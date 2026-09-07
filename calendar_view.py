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
    dt = datetime.strptime(f"{hour:02d}:00", "%H:%M")
    return dt.strftime("%-I %p") if hour != 0 else "12 AM"


def render_calendar_html(blocks, day_start: str, day_end: str) -> str:
    """Returns an HTML string ready for st.markdown(html, unsafe_allow_html=True)."""

    start_min = _minutes(day_start)
    end_min = _minutes(day_end)
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

    # Scheduled blocks (skip unscheduled ones — those render separately)
    block_divs = []
    scheduled = [b for b in blocks if not b.task.startswith("UNSCHEDULED")]
    for b in scheduled:
        try:
            b_start, b_end = _minutes(b.start), _minutes(b.end)
        except ValueError:
            continue
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
        {''.join(block_divs)}
    </div>
    """
    return html
