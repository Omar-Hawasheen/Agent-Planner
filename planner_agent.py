"""
Planner Agent
-------------
Takes a list of triaged tasks + fixed commitments for a day and produces a
structured daily schedule with a one-line rationale per block.

Two modes:
  1. LLM mode (default, if GROQ_API_KEY is set) — asks an LLM to reason about
     sequencing (deep work vs. quick tasks, energy levels, buffers) and
     return a strict JSON schedule. The output is validated; if it's invalid
     (overlaps a fixed commitment, goes outside the work day, etc.) the
     agent sends the error back to the LLM once and asks it to fix it.
  2. Rule-based fallback (no API key needed) — a simple greedy scheduler so
     the whole pipeline runs and is demoable even with zero setup.

This is the "Planner Agent" stage of a larger 3-agent pipeline
(Collector -> Triage -> Planner). It only needs the triaged task list and
the day's fixed commitments as input — see example_input.json.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Task:
    name: str
    priority: str          # "urgent" | "important" | "low"
    duration_minutes: int
    category: str          # e.g. "study", "project", "errand", "email"


@dataclass
class FixedCommitment:
    name: str
    start: str              # "HH:MM"
    end: str                # "HH:MM"


@dataclass
class ScheduleBlock:
    start: str
    end: str
    task: str
    rationale: str


PRIORITY_ORDER = {"urgent": 0, "important": 1, "low": 2}


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def _to_dt(hhmm: str) -> datetime:
    return datetime.strptime(hhmm, "%H:%M")


def _to_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


# --------------------------------------------------------------------------
# Validation (the "self-check" step)
# --------------------------------------------------------------------------

def validate_schedule(
    blocks: list[ScheduleBlock],
    fixed: list[FixedCommitment],
    day_start: str,
    day_end: str,
) -> list[str]:
    """Returns a list of problems found. Empty list = valid schedule."""
    problems = []
    day_start_dt, day_end_dt = _to_dt(day_start), _to_dt(day_end)

    parsed = []
    for b in blocks:
        try:
            s, e = _to_dt(b.start), _to_dt(b.end)
        except ValueError:
            problems.append(f"Block '{b.task}' has an unparseable time.")
            continue
        if s >= e:
            problems.append(f"Block '{b.task}' ends before it starts.")
            continue
        if s < day_start_dt or e > day_end_dt:
            problems.append(
                f"Block '{b.task}' ({b.start}-{b.end}) falls outside the "
                f"work day ({day_start}-{day_end})."
            )
        parsed.append((s, e, b.task))

    # check overlap with fixed commitments
    for s, e, name in parsed:
        for fc in fixed:
            fs, fe = _to_dt(fc.start), _to_dt(fc.end)
            if _overlaps(s, e, fs, fe):
                problems.append(
                    f"Block '{name}' ({_to_hhmm(s)}-{_to_hhmm(e)}) overlaps "
                    f"fixed commitment '{fc.name}' ({fc.start}-{fc.end})."
                )

    # check overlap between scheduled blocks themselves
    parsed_sorted = sorted(parsed, key=lambda x: x[0])
    for i in range(len(parsed_sorted) - 1):
        s1, e1, n1 = parsed_sorted[i]
        s2, e2, n2 = parsed_sorted[i + 1]
        if e1 > s2:
            problems.append(f"Blocks '{n1}' and '{n2}' overlap each other.")

    return problems


# --------------------------------------------------------------------------
# Rule-based fallback scheduler (no API key required)
# --------------------------------------------------------------------------

def rule_based_plan(
    tasks: list[Task],
    fixed: list[FixedCommitment],
    day_start: str,
    day_end: str,
) -> list[ScheduleBlock]:
    """Greedy scheduler: urgent first, longest deep-work tasks in the
    morning, short tasks batched together, working around fixed
    commitments. No LLM required."""

    day_start_dt, day_end_dt = _to_dt(day_start), _to_dt(day_end)

    # free windows = work day minus fixed commitments
    busy = sorted(
        [(_to_dt(fc.start), _to_dt(fc.end)) for fc in fixed], key=lambda x: x[0]
    )
    free_windows = []
    cursor = day_start_dt
    for fs, fe in busy:
        if fs > cursor:
            free_windows.append((cursor, fs))
        cursor = max(cursor, fe)
    if cursor < day_end_dt:
        free_windows.append((cursor, day_end_dt))

    # sort tasks: urgent > important > low, and within a tier, longer
    # (deep-work) tasks first so they land in the freshest window
    ordered = sorted(
        tasks,
        key=lambda t: (PRIORITY_ORDER.get(t.priority, 3), -t.duration_minutes),
    )

    blocks: list[ScheduleBlock] = []
    unscheduled: list[Task] = []

    for task in ordered:
        placed = False
        needed = timedelta(minutes=task.duration_minutes)
        for i, (ws, we) in enumerate(free_windows):
            if we - ws >= needed:
                block_start, block_end = ws, ws + needed
                rationale = _rationale_for(task, block_start)
                blocks.append(
                    ScheduleBlock(
                        start=_to_hhmm(block_start),
                        end=_to_hhmm(block_end),
                        task=task.name,
                        rationale=rationale,
                    )
                )
                # shrink the window
                free_windows[i] = (block_end, we)
                placed = True
                break
        if not placed:
            unscheduled.append(task)

    if unscheduled:
        names = ", ".join(t.name for t in unscheduled)
        blocks.append(
            ScheduleBlock(
                start="--:--",
                end="--:--",
                task=f"UNSCHEDULED: {names}",
                rationale="Didn't fit in remaining free time today — "
                           "consider moving to tomorrow or shortening scope.",
            )
        )

    return sorted(blocks, key=lambda b: b.start)


def _rationale_for(task: Task, block_start: datetime) -> str:
    if task.duration_minutes >= 90:
        return (
            f"Scheduled early/uninterrupted since it's a long "
            f"({task.duration_minutes}-min) deep-work item."
        )
    if task.priority == "urgent":
        return "Marked urgent, so placed as early as it would fit."
    if task.duration_minutes <= 20:
        return "Short task — batched into a lighter slot."
    return "Fit into an available window based on priority and length."


# --------------------------------------------------------------------------
# LLM mode (Groq) with one self-correction retry
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a scheduling agent. Given a list of tasks (with \
priority, duration, category) and a list of fixed commitments for the day, \
produce a JSON schedule.

Rules:
- Do not schedule anything during a fixed commitment.
- Do not schedule anything outside the given work day window.
- Put long deep-work tasks (>= 60 min) in the morning or right after the \
  first fixed commitment, when focus is freshest.
- Batch short tasks (<= 20 min) together rather than scattering them.
- Respect priority: urgent > important > low.
- If something genuinely does not fit, include it in "unscheduled" instead \
  of forcing an overlap.
- Give a short one-sentence rationale for each scheduled block.

Return ONLY valid JSON, no prose, no markdown fences, in this exact shape:
{
  "blocks": [
    {"start": "HH:MM", "end": "HH:MM", "task": "...", "rationale": "..."}
  ],
  "unscheduled": ["task name", ...]
}
"""


# Groq deprecates/renames models periodically. Override with the
# GROQ_MODEL env var (or a Streamlit secret of the same name) if this one
# gets retired again — check https://console.groq.com/docs/models for the
# current list.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def _call_groq(messages: list[dict], api_key: str) -> str:
    import urllib.request

    model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Groq's API sits behind Cloudflare, which blocks requests
            # with no User-Agent (returns a 403). Python's urllib sends
            # none by default, so we set one explicitly.
            "User-Agent": "planner-agent/1.0 (+https://github.com/)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def llm_plan(
    tasks: list[Task],
    fixed: list[FixedCommitment],
    day_start: str,
    day_end: str,
    api_key: str,
) -> list[ScheduleBlock]:
    user_prompt = json.dumps(
        {
            "day_start": day_start,
            "day_end": day_end,
            "fixed_commitments": [asdict(f) for f in fixed],
            "tasks": [asdict(t) for t in tasks],
        },
        indent=2,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = _call_groq(messages, api_key)
    blocks, unscheduled = _parse_llm_json(raw)
    problems = validate_schedule(blocks, fixed, day_start, day_end)

    if problems:
        # one self-correction pass: hand the errors back to the LLM
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": (
                    "That schedule has problems, fix them and return the "
                    "corrected JSON in the same format only:\n- "
                    + "\n- ".join(problems)
                ),
            }
        )
        raw2 = _call_groq(messages, api_key)
        blocks2, unscheduled2 = _parse_llm_json(raw2)
        problems2 = validate_schedule(blocks2, fixed, day_start, day_end)
        if not problems2:
            blocks, unscheduled = blocks2, unscheduled2
        # if still broken after one retry, fall through and return the
        # first attempt anyway — caller can see remaining problems via
        # validate_schedule() again if desired

    for name in unscheduled:
        blocks.append(
            ScheduleBlock(
                start="--:--",
                end="--:--",
                task=f"UNSCHEDULED: {name}",
                rationale="Model flagged this as not fitting today.",
            )
        )

    return sorted(blocks, key=lambda b: b.start)


def _parse_llm_json(raw: str) -> tuple[list[ScheduleBlock], list[str]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
    data = json.loads(cleaned)
    blocks = [
        ScheduleBlock(
            start=b["start"], end=b["end"], task=b["task"], rationale=b["rationale"]
        )
        for b in data.get("blocks", [])
    ]
    unscheduled = data.get("unscheduled", [])
    return blocks, unscheduled


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def plan_day(
    tasks: list[Task],
    fixed: list[FixedCommitment],
    day_start: str = "09:00",
    day_end: str = "18:00",
    force_mode: Optional[str] = None,
) -> tuple[list[ScheduleBlock], str, Optional[str]]:
    """Returns (blocks, mode_used, error). mode_used is 'llm' or
    'rule-based'. error is None on success, or a short message describing
    why the LLM path failed (if it did) even though a rule-based schedule
    is still returned so the caller always has something usable.

    force_mode: None (auto-detect based on GROQ_API_KEY presence, the
    original CLI behavior), "llm" (require the LLM path), or "rule-based"
    (skip the LLM entirely, e.g. when the user has explicitly chosen the
    free deterministic mode in the UI).
    """
    api_key = os.environ.get("GROQ_API_KEY")

    if force_mode == "rule-based":
        return rule_based_plan(tasks, fixed, day_start, day_end), "rule-based", None

    if force_mode == "llm":
        if not api_key:
            blocks = rule_based_plan(tasks, fixed, day_start, day_end)
            return blocks, "rule-based", "No GROQ_API_KEY is configured."
        try:
            blocks = llm_plan(tasks, fixed, day_start, day_end, api_key)
            return blocks, "llm", None
        except Exception as exc:
            blocks = rule_based_plan(tasks, fixed, day_start, day_end)
            return blocks, "rule-based", str(exc)

    # auto-detect (used by the CLI)
    if api_key:
        try:
            blocks = llm_plan(tasks, fixed, day_start, day_end, api_key)
            return blocks, "llm", None
        except Exception as exc:  # network/parsing failure -> fall back
            print(f"[planner_agent] LLM mode failed ({exc}), "
                  f"falling back to rule-based scheduler.", file=sys.stderr)
    return rule_based_plan(tasks, fixed, day_start, day_end), "rule-based", None


def render_markdown(blocks: list[ScheduleBlock], mode: str) -> str:
    lines = [f"# Daily Plan (generated by: {mode} mode)\n"]
    for b in blocks:
        lines.append(f"**{b.start}–{b.end}**  {b.task}")
        lines.append(f"> {b.rationale}\n")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python planner_agent.py <input.json> [day_start] [day_end]")
        sys.exit(1)

    input_path = sys.argv[1]
    day_start = sys.argv[2] if len(sys.argv) > 2 else "09:00"
    day_end = sys.argv[3] if len(sys.argv) > 3 else "18:00"

    with open(input_path) as f:
        raw = json.load(f)

    tasks = [Task(**t) for t in raw["tasks"]]
    fixed = [FixedCommitment(**f) for f in raw.get("fixed_commitments", [])]

    blocks, mode, error = plan_day(tasks, fixed, day_start, day_end)
    if error:
        print(f"[planner_agent] note: {error}", file=sys.stderr)

    md = render_markdown(blocks, mode)
    print(md)

    out_json = "plan_output.json"
    out_md = "plan_output.md"
    with open(out_json, "w") as f:
        json.dump([asdict(b) for b in blocks], f, indent=2)
    with open(out_md, "w") as f:
        f.write(md)

    print(f"\n(saved {out_json} and {out_md}, mode: {mode})", file=sys.stderr)


if __name__ == "__main__":
    main()
