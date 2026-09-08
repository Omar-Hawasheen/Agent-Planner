"""
Calendar view
-------------
Renders a list of ScheduleBlock objects as an HTML/CSS vertical day-timeline
(colored blocks positioned by time, hour gridlines on the left) — the same
visual idiom as Google Calendar's day/week view, scoped to a single day
since that's what the Planner Agent produces.

No external dependencies beyond what's already in the app; this is plain
HTML/CSS rendered via st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

from datetime import datetime

# A small fixed palette so colors are stable across reruns (keyed by a hash
# of the task name) rather than random each time.
PALETTE = [
    "#4285F4",  # blue
    "#EA4335",  # red
    "#34A853",  # green
    "#FBBC04",  # yellow
    "#9C27B0",  # purple
    "#FF6D01",  # orange
    "#00ACC1",  # cyan
    "#D81B60",  # pink
]

PX_PER_HOUR = 60


def _color_for(task_name: str) -> str:
    return PALETTE[hash(task_name) % len(PALETTE)]


def _minutes(hhmm: str) -> int:
    t = datetime.strptime(hhmm, "%H:%M")
    return t.hour * 60 + t.minute


def _format_hour_label(hour: int) -> str:
    # hour may be >= 24 (representing a time past midnight on a day that
    # wraps, e.g. day_end="00:00"); wrap it back into 0-23 purely for the
    # label text — the unwrapped value is still used for vertical position.
    h = hour % 24
    dt = datetime.strptime(f"{h:02d}:00", "%H:%M")
    return dt.strftime("%-I %p") if h != 0 else "12 AM"


def render_calendar_html(blocks, day_start: str, day_end: str, fixed=None) -> str:
    """Returns an HTML string ready for st.markdown(html, unsafe_allow_html=True).

    fixed: optional list of fixed commitments (each with .name/.start/.end,
    or dicts with the same keys) — rendered as distinct muted/striped
    blocks so they're visible on the timeline even though the scheduler
    treats them only as constraints, not as blocks it produces itself."""

    start_min = _minutes(day_start)
    raw_end_min = _minutes(day_end)
    # An end time at or before the start (e.g. day_end="00:00" meaning
    # midnight) means the day continues into the next calendar day rather
    # than being a zero/negative-length window.
    end_min = raw_end_min + 1440 if raw_end_min <= start_min else raw_end_min
    total_minutes = max(end_min - start_min, 60)
    total_height = int(total_minutes / 60 * PX_PER_HOUR)

    start_hour = start_min // 60
    end_hour = -(-end_min // 60)  # ceil

    # Hour gridlines + labels
    hour_lines = []
    for h in range(start_hour, end_hour + 1):
        top = int((h * 60 - start_min) / 60 * PX_PER_HOUR)
        if top < 0 or top > total_height:
            continue
        hour_lines.append(
            f'<div style="position:absolute; top:{top}px; left:0; right:0; '
            f'border-top:1px solid rgba(255,255,255,0.08); height:1px;"></div>'
            f'<div style="position:absolute; top:{max(top-8,0)}px; left:0; '
            f'width:52px; font-size:11px; color:rgba(255,255,255,0.45); '
            f'text-align:right; padding-right:8px;">{_format_hour_label(h)}</div>'
        )

    # Fixed commitments — rendered behind task blocks, visually distinct
    # (muted, striped) so it's clear they're constraints, not agent picks.
    fixed_divs = []
    for fc in (fixed or []):
        name = fc["name"] if isinstance(fc, dict) else fc.name
        fc_start = fc["start"] if isinstance(fc, dict) else fc.start
        fc_end = fc["end"] if isinstance(fc, dict) else fc.end
        try:
            f_start, f_end = _minutes(fc_start), _minutes(fc_end)
        except ValueError:
            continue
        if f_start < start_min:
            f_start += 1440
        if f_end < start_min:
            f_end += 1440
        top = int((f_start - start_min) / 60 * PX_PER_HOUR)
        height = max(int((f_end - f_start) / 60 * PX_PER_HOUR), 22)
        fixed_divs.append(
            f'<div title="Fixed commitment" style="'
            f'position:absolute; top:{top}px; left:60px; right:8px; '
            f'height:{height}px; background:repeating-linear-gradient('
            f'45deg, rgba(255,255,255,0.06), rgba(255,255,255,0.06) 6px, '
            f'rgba(255,255,255,0.02) 6px, rgba(255,255,255,0.02) 12px); '
            f'border:1px dashed rgba(255,255,255,0.3); border-radius:6px; '
            f'padding:4px 8px; overflow:hidden;">'
            f'<div style="font-size:12px; font-weight:600; '
            f'color:rgba(255,255,255,0.75); line-height:1.2; '
            f'white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">'
            f'{fc_start}–{fc_end}  ·  {name} (fixed)</div>'
            f'</div>'
        )

    # Scheduled blocks (skip unscheduled ones — those render separately)
    block_divs = []
    scheduled = [b for b in blocks if not b.task.startswith("UNSCHEDULED")]
    for b in scheduled:
        try:
            b_start, b_end = _minutes(b.start), _minutes(b.end)
        except ValueError:
            continue
        # Same wraparound logic as above: a block time earlier than the
        # day's start must belong to the portion past midnight.
        if b_start < start_min:
            b_start += 1440
        if b_end < start_min:
            b_end += 1440
        top = int((b_start - start_min) / 60 * PX_PER_HOUR)
        height = max(int((b_end - b_start) / 60 * PX_PER_HOUR), 22)
        color = _color_for(b.task)
        block_divs.append(
            f'<div title="{b.rationale}" style="'
            f'position:absolute; top:{top}px; left:60px; right:8px; '
            f'height:{height}px; background:{color}; border-radius:6px; '
            f'padding:4px 8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.3);">'
            f'<div style="font-size:12px; font-weight:600; color:white; '
            f'line-height:1.2; white-space:nowrap; text-overflow:ellipsis; '
            f'overflow:hidden;">{b.start}–{b.end}  ·  {b.task}</div>'
            f'</div>'
        )

    html = f"""
    <div style="position:relative; height:{total_height}px; margin-left:4px;
                margin-top:8px; margin-bottom:16px;
                border-left:1px solid rgba(255,255,255,0.08);">
        {''.join(hour_lines)}
        {''.join(fixed_divs)}
        {''.join(block_divs)}
    </div>
    """
    return html
