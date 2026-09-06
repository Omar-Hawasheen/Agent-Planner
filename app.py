"""
Planner Agent — Web Interface
------------------------------
A small Streamlit app that sits on top of planner_agent.py so you can:
  - add tasks and fixed commitments through a form (no JSON editing)
  - optionally plug in a Groq API key for real LLM reasoning
  - generate a schedule and see it rendered as a timeline with rationale
  - see clearly whether the LLM or the rule-based fallback produced it

Run locally:
    pip install streamlit
    streamlit run app.py

Deploy for free:
    Push this folder to a GitHub repo and deploy on
    https://share.streamlit.io (Streamlit Community Cloud, free tier).
"""

import json
import datetime as dt
from dataclasses import asdict

import streamlit as st

from planner_agent import (
    Task,
    FixedCommitment,
    plan_day,
)

st.set_page_config(page_title="Planner Agent", page_icon="🗓️", layout="wide")

# --------------------------------------------------------------------------
# Session state setup
# --------------------------------------------------------------------------

if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "commitments" not in st.session_state:
    st.session_state.commitments = []
if "result" not in st.session_state:
    st.session_state.result = None
if "mode_used" not in st.session_state:
    st.session_state.mode_used = None


def load_example():
    st.session_state.tasks = [
        {"name": "Work on HPC project pipeline", "priority": "urgent", "duration_minutes": 120, "category": "project"},
        {"name": "Reply to unread emails", "priority": "important", "duration_minutes": 20, "category": "email"},
        {"name": "Review Discrete Math homework", "priority": "important", "duration_minutes": 45, "category": "study"},
        {"name": "Buy groceries", "priority": "low", "duration_minutes": 30, "category": "errand"},
        {"name": "Read one paper for stats course", "priority": "low", "duration_minutes": 40, "category": "study"},
    ]
    st.session_state.commitments = [
        {"name": "HPC & Big Data lecture", "start": "10:00", "end": "11:30"},
        {"name": "Badminton", "start": "17:00", "end": "18:30"},
    ]
    st.session_state.result = None


# --------------------------------------------------------------------------
# Sidebar — settings
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    plan_date = st.date_input("Plan for", value=dt.date.today())

    day_start_t = st.time_input(
        "Day starts", value=dt.time(9, 0), step=dt.timedelta(minutes=15)
    )
    day_end_t = st.time_input(
        "Day ends", value=dt.time(18, 0), step=dt.timedelta(minutes=15)
    )
    day_start = day_start_t.strftime("%H:%M")
    day_end = day_end_t.strftime("%H:%M")

    st.divider()
    st.caption(
        "Optional — leave blank to use the deterministic rule-based "
        "scheduler (no cost, no setup). Add a free Groq key to get real "
        "LLM reasoning instead."
    )
    groq_key = st.text_input("GROQ_API_KEY", type="password", value="")
    if groq_key:
        import os
        os.environ["GROQ_API_KEY"] = groq_key

    st.divider()
    if st.button("Load example day"):
        load_example()
        st.rerun()

# --------------------------------------------------------------------------
# Main layout
# --------------------------------------------------------------------------

st.title("🗓️ Planner Agent")
st.caption(
    "Part of a Collector → Triage → **Planner** agent pipeline. This screen "
    "drives the Planner Agent: add tasks and fixed commitments, then "
    "generate a validated daily schedule with reasoning per block."
)

col1, col2 = st.columns(2)

# ---- Fixed commitments -----------------------------------------------
with col1:
    st.subheader("Fixed commitments")
    with st.form("add_commitment", clear_on_submit=True):
        c_name = st.text_input("Name", key="c_name")
        cc1, cc2 = st.columns(2)
        c_start_t = cc1.time_input(
            "Start", value=dt.time(10, 0), step=dt.timedelta(minutes=15), key="c_start"
        )
        c_end_t = cc2.time_input(
            "End", value=dt.time(11, 0), step=dt.timedelta(minutes=15), key="c_end"
        )
        if st.form_submit_button("Add commitment") and c_name:
            st.session_state.commitments.append(
                {
                    "name": c_name,
                    "start": c_start_t.strftime("%H:%M"),
                    "end": c_end_t.strftime("%H:%M"),
                }
            )

    for i, c in enumerate(st.session_state.commitments):
        row = st.container(border=True)
        rc1, rc2 = row.columns([5, 1])
        rc1.write(f"**{c['name']}** — {c['start']}–{c['end']}")
        if rc2.button("✕", key=f"del_c_{i}"):
            st.session_state.commitments.pop(i)
            st.rerun()

# ---- Tasks --------------------------------------------------------------
with col2:
    st.subheader("Tasks")
    with st.form("add_task", clear_on_submit=True):
        t_name = st.text_input("Name", key="t_name")
        tc1, tc2, tc3 = st.columns(3)
        t_priority = tc1.selectbox("Priority", ["urgent", "important", "low"], key="t_priority")
        t_duration = tc2.number_input("Minutes", min_value=5, max_value=480, value=30, step=5, key="t_duration")
        t_category = tc3.text_input("Category", value="task", key="t_category")
        if st.form_submit_button("Add task") and t_name:
            st.session_state.tasks.append(
                {
                    "name": t_name,
                    "priority": t_priority,
                    "duration_minutes": int(t_duration),
                    "category": t_category,
                }
            )

    for i, t in enumerate(st.session_state.tasks):
        row = st.container(border=True)
        rc1, rc2 = row.columns([5, 1])
        rc1.write(
            f"**{t['name']}** — {t['priority']}, {t['duration_minutes']} min, {t['category']}"
        )
        if rc2.button("✕", key=f"del_t_{i}"):
            st.session_state.tasks.pop(i)
            st.rerun()

st.divider()

# ---- Generate -------------------------------------------------------------

generate = st.button("🚀 Generate plan", type="primary", use_container_width=True)

if generate:
    if not st.session_state.tasks:
        st.warning("Add at least one task first.")
    else:
        tasks = [Task(**t) for t in st.session_state.tasks]
        commitments = [FixedCommitment(**c) for c in st.session_state.commitments]
        with st.spinner("Planning your day..."):
            blocks, mode = plan_day(tasks, commitments, day_start, day_end)
        st.session_state.result = blocks
        st.session_state.mode_used = mode

# ---- Results ----------------------------------------------------------

if st.session_state.result:
    mode = st.session_state.mode_used
    badge = "🤖 LLM reasoning" if mode == "llm" else "⚙️ Rule-based fallback"
    st.subheader(f"Plan for {plan_date.strftime('%A, %B %d')}")
    st.caption(badge)

    for b in st.session_state.result:
        unscheduled = b.task.startswith("UNSCHEDULED")
        box = st.container(border=True)
        if unscheduled:
            box.markdown(f"⚠️ **{b.task}**")
        else:
            box.markdown(f"**{b.start}–{b.end}**  ·  {b.task}")
        box.caption(b.rationale)

    with st.expander("Raw JSON output"):
        st.code(json.dumps([asdict(b) for b in st.session_state.result], indent=2), language="json")
