"""
Google Calendar integration
----------------------------
Minimal OAuth2 "authorization code" flow + event creation, using plain
`requests` calls against Google's endpoints directly (no google-api-python-
client dependency, to keep this simple to read and audit).

This deliberately writes to the *visitor's own* Google Calendar, not the
developer's — each visitor authorizes individually. That means:

  - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (from a free Google Cloud
    project) are safe to keep in Streamlit Secrets, same as the Groq key —
    they identify *your app*, not any one user's calendar.
  - GOOGLE_REDIRECT_URI must exactly match a URI registered in that
    project's OAuth client (e.g. your Streamlit Cloud app's URL).
  - While the OAuth consent screen is in "Testing" mode (the default,
    free, no-review-needed setting), only Google accounts you've explicitly
    added as test users (up to 100) can complete the login. Anyone else
    sees an access-blocked screen. Making it open to arbitrary public
    visitors requires Google's app verification process — out of scope
    for a portfolio/demo project, and worth saying so in an interview.

Tokens are kept only in Streamlit's session state (memory, per browser
session) — nothing is written to disk, and a server restart or new
session means reconnecting.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import requests

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = "https://www.googleapis.com/auth/calendar.events " \
         "https://www.googleapis.com/auth/userinfo.email"


def build_auth_url(client_id: str, redirect_uri: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "online",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return f"{AUTH_ENDPOINT}?{query}"


def exchange_code_for_token(
    client_id: str, client_secret: str, redirect_uri: str, code: str
) -> dict:
    """Returns {'access_token': ..., 'expires_in': ..., ...} or raises on
    failure (e.g. an expired/one-time-use code being replayed)."""
    resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_email(access_token: str) -> Optional[str]:
    try:
        resp = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("email")
    except Exception:
        return None


def create_event(
    access_token: str,
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    timezone: str,
    description: str = "",
    color_id: Optional[str] = None,
) -> dict:
    """color_id: one of Google Calendar's 11 fixed event colors ("1"-"11").
    See EVENT_COLORS below for the name each number maps to. Omit to use
    the calendar's default color."""
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
    }
    if color_id:
        body["colorId"] = color_id
    resp = requests.post(
        CALENDAR_EVENTS_ENDPOINT,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# Google Calendar's fixed event-color palette — colorId is always "1".."11",
# never a hex code. Order chosen so adjacent numbers look visually distinct.
EVENT_COLORS = ["9", "11", "10", "5", "3", "7", "6", "2", "4", "1"]
FIXED_COMMITMENT_COLOR = "8"  # Graphite — consistent, muted, same idea as
                              # the dashed/striped style used in-app


def color_for(name: str) -> str:
    """Deterministic colorId for a task name, so the same task keeps the
    same color across a retry rather than jumping around."""
    return EVENT_COLORS[hash(name) % len(EVENT_COLORS)]
