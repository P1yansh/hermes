# Hermes

Autonomous academic triage and opportunity radar for university students and developers, built as an extension layer for the Athena workspace.

Built for the **Hacktoberfest 2026 Week 3: Slow and Steady** challenge.

---

## Why I Built This

I have a recurring problem every semester: I miss assignment deadlines and hackathon cutoffs because my inbox is flooded with university spam, society announcements, and course portal notifications. Important submission cutoffs sit buried beneath bookstore promotions and club flyers until someone in a group chat mentions they're finishing their submission.

Hermes runs in the background and takes care of this:
1. **Academic Triage**: Pulls Google Classroom coursework and unread emails, drops marketing noise, and runs local Gemma 2 to extract the course, title, and exact deadline timestamp into clean JSON.
2. **Opportunity Scout**: Crawls hackathons, fellowships, and internships, then scores them against your specific technical skills (Python, systems, AI agents).
3. **Urgency Radar**: Aggregates assignments and closing registrations into three time-to-cutoff bands:
   - 🔴 **Panic** (`< 24 hours`)
   - 🟡 **Imminent** (`24h - 72h`)
   - 🟢 **Upcoming** (`> 72h`)
4. **Morning Voice Briefing**: Generates a 60-second summary script and synthesizes it into an MP3 via ElevenLabs, so you can listen to your morning status without opening five course dashboards.

---

## Why Open AI Models Matter Here

- **Student Privacy**: Academic records, professor emails, and coursework shouldn't be sent to proprietary commercial cloud LLMs. Hermes runs against open-weight Gemma 2 locally on your own machine.
- **Zero Ongoing Cost**: Running locally on an RTX 4050 (or CPU) means no recurring token charges or subscription tiers.
- **Offline Resilience**: The system includes deterministic heuristic parsers. Even if your internet drops or the local inference engine is paused, tests and task extractions still run.

---

## System Design

```
   [ Gmail API / IMAP ]           [ Google Classroom ]
            │                              │
            └──────────────┬───────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
   [ MockDatasetLoader ]       [ GoogleLiveConnector ]
   (Test/Judge Fixtures)       (OAuth2 Classroom & Mail)
             │                           │
             └─────────────┬─────────────┘
                           ▼
              [ Academic Triage Agent ]
                           │
       [ Local Gemma 2 9B via Athena llama-server ]
                           │
                           ▼
               [ Urgency Radar Engine ]
              (Sorted by hours remaining)
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   [ ElevenLabs TTS Engine ]   [ FastAPI REST Backend ]
    (Morning MP3 Briefing)       (Render Deployment)
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

# Start the development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI docs will be available at `http://localhost:8000/docs`.

---

## Configuration

Settings are configured via `.env`:

| Key | Default | Description |
| :--- | :--- | :--- |
| `DATA_SOURCE` | `mock` | `mock` uses relative time-anchored test fixtures; `live` uses Google OAuth. |
| `LOCAL_LLM_URL` | `http://127.0.0.1:8080/v1` | Local OpenAI-compatible llama.cpp endpoint. |
| `LOCAL_LLM_MODEL` | `gemma-2-9b-it` | Model identifier for local prompt routing. |
| `ELEVENLABS_API_KEY`| `""` | ElevenLabs API key (falls back to local audio if omitted). |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | Voice ID used for daily briefing generation. |

---

## Running Tests

Run the non-interactive test suite:

```bash
uv run pytest -v
```

All 13 tests cover the mock loader, urgency radar calculation, triage agent, and HTTP endpoints.

---

## API Endpoints

- `GET /` — System status, active model, and health info.
- `GET /api/triage` — Extracted academic assignments and email tasks.
- `GET /api/scout` — Scored hackathons and internships.
- `POST /api/scout` — Filter opportunities with a custom developer skill profile.
- `GET /api/radar` — Unified urgency matrix sorted by time-to-deadline.
- `GET /api/briefing` — Conversational morning script generated from active radar.
- `GET /api/briefing/audio` — Streams or downloads the synthesized ElevenLabs MP3.

---

## Deployment

A `render.yaml` blueprint is included for 1-click deployment on Render:
1. Connect your repository to Render.
2. Select **New Blueprint Instance**.
3. Render runs `pip install uv && uv sync` and starts the Uvicorn web service.

---

## License

MIT
