# Planner Agent

The "Planner" stage of a Collector → Triage → **Planner** daily-task agent
pipeline. Given a list of triaged tasks and your fixed commitments for the
day, it produces a structured schedule with a one-line rationale per block —
and it validates its own output before returning it.

## What makes this "agentic" rather than a single prompt

- **Structured handoff**: it takes a defined input schema (tasks +
  commitments) and returns a defined output schema (time blocks + reasons),
  so it could sit behind a Collector Agent and a Triage Agent in a real
  pipeline.
- **Self-check loop**: after the LLM proposes a schedule, `validate_schedule()`
  checks it against your actual constraints (no overlaps, stays inside the
  work day). If it's wrong, the agent sends the *specific* errors back to the
  LLM and asks for a corrected version — one retry, not silent failure.
- **Graceful fallback**: if no API key is set (or the API call fails), it
  falls back to a deterministic rule-based scheduler so the tool always
  produces a usable plan, even offline.

## Quick start — command line (zero setup, no API key)

```bash
python3 planner_agent.py example_input.json
```

This runs the rule-based scheduler and prints a markdown plan, also saved to
`plan_output.md` / `plan_output.json`.

## Quick start — web interface

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens a local page where you can add tasks and fixed commitments through a
form, hit "Generate plan", and see the schedule rendered as a timeline with
the rationale for each block. There's a "Load example day" button to see it
work instantly, and a sidebar toggle to switch between:

- **Rule-based** — deterministic, no API key needed, always works.
- **AI Agent** — real LLM reasoning via Groq, using the key configured in
  Secrets (see below). Visitors never see or enter a key themselves.

### Setting up your Groq key (kept out of the public repo)

The app reads the key from Streamlit's secrets store, never from a visible
text box, so it's safe to make the repo public:

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and
   put your real key in it. This file is git-ignored — it will never be
   committed.
2. For local runs, that's it — `streamlit run app.py` picks it up
   automatically.
3. For the deployed app, add the same line under your app's
   **Settings → Secrets** on Streamlit Community Cloud:
   ```
   GROQ_API_KEY = "gsk_your_key_here"
   ```
   Every visitor to your deployed app can then select "AI Agent" mode and
   it just works, powered by your key, without them ever seeing it.

If you ever paste a real key somewhere public by mistake (a commit, a
screenshot, a chat), treat it as compromised and rotate it from the Groq
console — old keys can be revoked and a new one generated in seconds.

### Setting up Google Calendar sync (optional)

Accepting a plan can push it straight into your Google Calendar. This
needs a free Google Cloud project — about 10 minutes, one-time:

1. Go to https://console.cloud.google.com, create a new project (free).
2. **APIs & Services → Library** → search "Google Calendar API" → Enable.
3. **APIs & Services → OAuth consent screen** → choose "External" →
   fill in an app name and your email → add the scope
   `https://www.googleapis.com/auth/calendar.events` → under "Test users",
   add your own Google account (and anyone else you want able to connect).
   Leaving the app in "Testing" status is fine and free — it just means
   only accounts you've listed as test users can sign in, which is exactly
   right for a portfolio demo.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type: "Web application" → under "Authorized redirect
   URIs" add your deployed app's exact URL (e.g.
   `https://your-app.streamlit.app`) and, if you want to test locally too,
   `http://localhost:8501`.
5. Copy the generated **Client ID** and **Client Secret**.
6. Add all three to Secrets (same place as `GROQ_API_KEY`, either your
   local `.streamlit/secrets.toml` or Streamlit Cloud's Settings → Secrets):
   ```
   GOOGLE_CLIENT_ID = "your_client_id"
   GOOGLE_CLIENT_SECRET = "your_client_secret"
   GOOGLE_REDIRECT_URI = "https://your-app.streamlit.app"
   ```

Each visitor connects *their own* Google account (the app never touches
your calendar) — "Connect Google Calendar" in the sidebar sends them
through Google's real consent screen, and only after they approve does
"Accept & sync" become clickable.

**Known limitation:** the OAuth redirect briefly sends the browser to
Google and back. Streamlit's session usually survives that round trip,
but if you find your tasks disappeared after connecting, that's why —
just click "Load example day" or re-add your tasks, connect first next
time, then generate. Worth mentioning as a known trade-off if it comes up
in an interview, not a bug you need to hide.

### Deploying it for free (so you have a live link, not just local)

1. Push this folder to a public GitHub repo.
2. Go to https://share.streamlit.io, sign in with GitHub, and point it at
   the repo (`app.py` as the entry point).
3. You get a free hosted URL you can put directly in your resume/portfolio.

## With real LLM reasoning

1. Get a free API key at https://console.groq.com (Groq's free tier is
   generous and fast — no credit card required).
2. `export GROQ_API_KEY=your_key_here`
3. Run the same command — it will automatically use the LLM instead of the
   fallback.

## Input format (`example_input.json`)

```json
{
  "fixed_commitments": [
    {"name": "Lecture", "start": "10:00", "end": "11:30"}
  ],
  "tasks": [
    {"name": "Finish project", "priority": "urgent", "duration_minutes": 120, "category": "project"}
  ]
}
```

`priority` is one of `urgent` / `important` / `low`.

## Optional day window

```bash
python3 planner_agent.py example_input.json 08:00 20:00
```

Defaults to `09:00`–`18:00`.

## Where this fits in the bigger pipeline

This is one file in a larger idea: a **Collector Agent** (pulls real tasks
from Google Tasks/Calendar or an email inbox) → **Triage Agent** (an LLM
call that classifies raw items into this Planner's input schema) →
**Planner Agent** (this file). For a quick resume project, this Planner
Agent alone — demoed against a hand-written `example_input.json` — is
already a complete, demoable piece of agent orchestration: LLM call →
validation → self-correction → structured output.

## What's new: calendar view, Retry, and Google Calendar sync

- **Visual timeline** — the schedule renders as a colored day-timeline
  (Google Calendar's day-view look), not just a list.
- **Retry** — regenerates a different valid schedule. In AI Agent mode the
  model is explicitly shown the previous arrangement and asked for a
  different one; in rule-based mode, ties between equal-priority tasks are
  shuffled so you don't get the identical result twice.
- **Accept & sync to Google Calendar** — once you're happy with a plan,
  this pushes each block as a real event on your own Google Calendar (see
  setup above).

## Resume line

"Built a Python planning agent that takes structured task/priority data and
produces a validated daily schedule via LLM reasoning, with automatic
self-correction when the proposed schedule violates constraints, and a
deterministic fallback for zero-dependency demos."
