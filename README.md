# Hermes

Autonomous academic triage and opportunity radar for university students and developers, built as an extension layer for the Athena workspace.

Built for the **Hacktoberfest 2026 Week 3: Slow and Steady** challenge.

---

## Why I Built This

I have a recurring problem every semester: I miss assignment deadlines and hackathon cutoffs because my inbox is flooded with university spam, society announcements, and course portal notifications. Important submission cutoffs sit buried beneath bookstore promotions and club flyers until someone in a group chat mentions they're finishing their submission.

Hermes runs in the background and takes care of this:
1. **Academic Triage Agent**: Pulls Google Classroom coursework and unread emails, drops marketing noise through a fast Stage-1 header/keyword pre-filter, and runs local Gemma 2 to extract the course, title, and exact deadline timestamp.
2. **Opportunity Scout Agent**: Crawls hackathons, fellowships, and internships, then scores them against your specific technical skills (Python, systems, AI agents).
3. **Decoupled SQLite Cache**: Stores seen IDs to prevent re-evaluating identical emails, making all query endpoints return in `< 5ms`.
4. **Sloth Urgency Radar**: Aggregates assignments and closing registrations into three time-to-cutoff bands with honest status quotes:
   - 🔴 **Panic** (`< 6 hours`): *"jaldi kar alsi, warna gaya bas {x} hours baki hai"*
   - 🟡 **Approaching** (`6h - 24 hours`): *"abhi to {x} ghante hai :)"*
   - 🟢 **Chill** (`> 24 hours`): *"abhi kyu karna, {x} days baki hai"*
5. **Morning Voice Briefing**: Generates a 60-second summary script and synthesizes it into an MP3 via ElevenLabs (with deterministic content-addressable caching to protect API quotas), so you can listen to your morning status without opening five course dashboards.
6. **Embedded Dark Dashboard**: A single-page, glassmorphic UI served directly by FastAPI at `http://localhost:8000/`, with one-click inbox syncing, urgency swimlanes, and an inline audio briefing player.

---

## Two Deployment Topologies

Hermes is built to accommodate two distinct deployment environments:

1. **Local Daemon Mode (`RUN_MODE=local`, `DATA_SOURCE=live`)**
   - Runs locally on your workstation as an Athena agent daemon.
   - Connects to local `llama-server` on your GPU (e.g. RTX 4050 6GB) at `http://127.0.0.1:8080/v1` running open-weight `gemma-2-9b-it`.
   - Ingests real university emails and Google Classroom tasks via OAuth2 tokens stored on your disk.
   - Guaranteed 100% data privacy: your grades and emails never touch external AI servers.

2. **Cloud Judge Sandbox (`RUN_MODE=cloud_sandbox`, `DATA_SOURCE=mock`)**
   - Deployed on Render for Hacktoberfest judges and community testing.
   - Uses `MockDatasetLoader` with dynamic timestamps relative to UTC `now` and deterministic fallback parsers.
   - Allows judges to test the full multi-agent pipeline, urgency radar, and audio streaming without requiring university logins or local GPU access.

---

## System Design

```text
  [ Gmail API / Classroom ]       [ Opportunity Feeds / Mock JSON ]
              │                                   │
   ┌──────────┴──────────┐                        │
   ▼                     ▼                        ▼
[MockDatasetLoader] [GoogleLiveConnector]   [OpportunityConnector]
   │                     │                        │
   └──────────┬──────────┘                        │
              ▼                                   ▼
   [ Academic Triage Agent ]            [ Opportunity Scout Agent ]
   (Header Pre-filter + Regex)          (Skill & Stack Scorer)
              │                                   │
   [ Local Gemma 2 9B (llama-server / GBNF) ]     │
              │                                   │
              └─────────────────┬─────────────────┘
                                ▼
                    [ SQLite State & Cache ]
                    (Deduplication & Storage)
                                │
                                ▼
                     [ Urgency Radar Engine ]
                  (Panic <6h | Approaching | Chill)
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
       [ Briefing Engine + TTS ]    [ FastAPI REST Backend ]
      (ElevenLabs / Local Cache)     (/radar, /triage, /scout, /sync)
```

---

## Prerequisites

- Python 3.11+
- [Astral `uv`](https://astral.sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- (Optional for local inference) `llama-server` running Gemma 2 at `http://127.0.0.1:8080/v1`

---

## Quickstart

```bash
# Clone the repository
git clone https://github.com/P1yansh/hermes.git
cd hermes

# Sync environment using uv (takes < 1 second)
uv sync

# Copy environment variables
cp .env.example .env

# Start the development server (automatically runs initial sync on startup)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## Configuration

Settings are configured via `.env`:

| Key | Default | Description |
| :--- | :--- | :--- |
| `RUN_MODE` | `local` | `local` (workstation daemon) or `cloud_sandbox` (Render demo). |
| `DATA_SOURCE` | `mock` | `mock` uses relative time-anchored test fixtures; `live` uses Google OAuth. |
| `USER_TIMEZONE` | `Asia/Kolkata` | Local timezone used to normalize naive email deadlines into UTC. |
| `DATABASE_PATH` | `data/hermes.db` | Local SQLite database location. |
| `LOCAL_LLM_URL` | `http://127.0.0.1:8080/v1` | Local OpenAI-compatible llama.cpp endpoint. |
| `LOCAL_LLM_MODEL` | `gemma-2-9b-it` | Model identifier for local prompt routing. |
| `ELEVENLABS_API_KEY`| `""` | ElevenLabs API key (falls back to local audio if omitted). |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | Voice ID used for daily briefing generation. |

---

## Running Tests

Run the test suite with `uv`:

```bash
uv run pytest -v
```

All 22 unit and integration tests cover SQLite persistence, Stage-1 triage filtering, opportunity matching edge cases, urgency radar calculations, and HTTP endpoints.

---

## API Endpoints

- `GET /` — Serves the embedded single-page dashboard UI (HTML) or returns system health/metadata (JSON).
- `POST /api/sync` — Triggers an on-demand ingestion and triage sync (`force=true` supported).
- `GET /api/triage` — Extracted academic assignments and email tasks from SQLite cache.
- `GET /api/scout` — Scored hackathons and internships.
- `POST /api/scout` — Filter opportunities with a custom developer skill profile.
- `GET /api/radar` — Unified urgency matrix sorted chronologically.
- `GET /api/briefing` — Conversational morning script generated from active radar.
- `GET /api/briefing/audio` — Streams or downloads the content-cached ElevenLabs MP3.

---

## Deployment

A `render.yaml` blueprint is included for 1-click deployment on Render:
1. Connect your repository to Render.
2. Select **New Blueprint Instance**.
3. Render runs `pip install uv && uv sync` and starts the Uvicorn web service.

---

## License

MIT
