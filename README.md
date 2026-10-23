# Hermes

Autonomous academic triage and opportunity radar for university students and developers, built as an extension layer for the Athena workspace.

Built for the **Hacktoberfest 2026 Week 3: Slow and Steady** challenge.

---

## Why I Built This

I have a recurring problem every semester: I miss assignment deadlines and hackathon cutoffs because my inbox is flooded with university spam, society announcements, and course portal notifications. Important submission cutoffs sit buried beneath bookstore promotions and club flyers until someone in a group chat mentions they're finishing their submission.

Hermes runs in the background and takes care of this:
1. **Academic Triage Agent**: Pulls Google Classroom coursework and unread emails, drops marketing noise through a fast Stage-1 header/keyword pre-filter, and runs local Gemma 3 4B to extract the course, title, and exact deadline timestamp. Relative phrases such as "tonight" are anchored to the email's IST timestamp, not the current wall clock.
2. **Opportunity Scout Agent**: Crawls hackathons, fellowships, and internships, then scores them against your specific technical skills (Python, systems, AI agents).
3. **Decoupled SQLite Cache**: Stores seen IDs to prevent re-evaluating identical emails. Dashboard reads come from SQLite, not from an LLM call.
4. **Sloth Urgency Radar**: Aggregates assignments and closing registrations into three time-to-cutoff bands with honest status quotes:
   - 🔴 **Panic** (`< 6 hours`): *"jaldi kar alsi, warna gaya bas {x} hours baki hai"*
   - 🟡 **Approaching** (`6h - 24 hours`): *"abhi to {x} ghante hai :)"*
   - 🟢 **Chill** (`> 24 hours`): *"abhi kyu karna, {x} days baki hai"*
5. **Morning Voice Briefing**: Generates a 60-second Hinglish summary script and synthesizes it into an MP3 via ElevenLabs, with content-addressable caching. If ElevenLabs is not configured or the request fails, the API returns `503` and the dashboard falls back to browser speech synthesis. No silent placeholder MP3 is written to the cache.
6. **Embedded Dark Dashboard**: A single-page, glassmorphic UI served directly by FastAPI at `http://localhost:8000/`, with one-click inbox syncing, urgency swimlanes, and an inline audio briefing player.

---

## Two Deployment Topologies

Hermes is built to accommodate two distinct deployment environments:

1. **Local Daemon Mode (`RUN_MODE=local`, `DATA_SOURCE=live`)**
   - Runs locally on your workstation as an Athena agent daemon.
   - Connects to local `llama-server` on your GPU (e.g. RTX 4050 6GB) at `http://127.0.0.1:8080/v1` running open-weight `gemma-3-4b-it` (Q4_K_M).
   - Ingests real university emails and Google Classroom tasks via OAuth2 tokens stored on your disk.
   - LLM inference stays on the machine. If ElevenLabs is enabled, the generated briefing script (not raw email bodies) is sent to ElevenLabs for speech synthesis. Leave `ELEVENLABS_API_KEY` empty for a fully local path and let the browser speak the script.

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
   [ Local Gemma 3 4B (llama-server / GBNF) ]     │
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
- (Optional for local inference) `llama-server` running Gemma 3 4B at `http://127.0.0.1:8080/v1`

---

## Quickstart

```bash
# Clone the repository
git clone https://github.com/P1yansh/hermes.git
cd hermes

# Sync environment using uv (takes < 1 second)
uv sync

# Copy environment variables and the account manifest template
cp .env.example .env
cp config/accounts.example.json config/accounts.json

# Start the development server (automatically runs initial sync on startup)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## Local Model Telemetry

The dashboard reads `GET /api/telemetry/gemma` instead of showing guessed numbers. The endpoint probes `llama-server`, reads the model metadata, and reports measured tokens/sec, prompt latency, context size, and VRAM when `nvidia-smi` is available.

To print the same numbers from a terminal:

```bash
uv run python scripts/bench_gemma.py
```

On the RTX 4050 6GB test machine with `gemma-3-4b-it` Q4_K_M, the probe measured about 50 tokens/sec. A full email extraction took 3.3s; the briefing script took 4.1s. Those numbers move with prompt length and GPU state, so the endpoint reports live values rather than a fixed label.

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
| `LOCAL_LLM_MODEL` | `gemma-3-4b-it` | Model identifier for local prompt routing. |
| `ELEVENLABS_API_KEY`| `""` | ElevenLabs API key. When empty, `/api/briefing/audio` returns `503` and the UI uses browser speech. |
| `ELEVENLABS_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` | Voice ID used for daily briefing generation. |

`config/accounts.json` holds your inbox labels and token paths, so it is ignored by git. Start from `config/accounts.example.json` and keep the real file local. The example contains placeholders only.

---

## Running Tests

Run the test suite with `uv`:

```bash
uv run pytest -v
```

The suite runs 61 tests in under a second. It covers SQLite WAL mode and connection cleanup, atomic ledger/task writes, missing-deadline handling, IST relative-date anchoring, Stage-1 triage filtering, opportunity matching, urgency radar bands, ElevenLabs failure paths, and HTTP endpoints. No test calls llama-server, ElevenLabs, or a public API; network clients are patched in `tests/conftest.py`.

To fail the run on leaked SQLite handles:

```bash
uv run pytest -v -W error::ResourceWarning
```

---

## API Endpoints

- `GET /` — Serves the embedded single-page dashboard UI (HTML) or returns system health/metadata (JSON).
- `POST /api/sync` — Polls connectors, checks the email ledger, and runs an incremental triage pass. `force=true` re-evaluates ledger entries.
- `GET /api/triage` — Extracted academic assignments and email tasks from SQLite cache.
- `GET /api/scout` — Scored hackathons and internships. Ineligible rows are filtered out.
- `POST /api/scout` — Filter opportunities with a custom developer skill profile.
- `GET /api/radar` — Unified urgency matrix sorted chronologically. Items without a deadline go to the watchlist, never a fabricated band.
- `GET /api/briefing` — Hinglish morning script generated from the active radar, plus the real SHA-256 audio cache key.
- `GET /api/briefing/audio` — Streams the cached ElevenLabs MP3. Returns `503` when synthesis is unavailable so the UI can fall back to browser speech.
- `GET /api/telemetry/gemma` — Live llama-server probe: model, quantization, tokens/sec, prompt latency, context size, and VRAM if `nvidia-smi` is available.

---

## Deployment

A `render.yaml` blueprint is included for 1-click deployment on Render:
1. Connect your repository to Render.
2. Select **New Blueprint Instance**.
3. Set `ELEVENLABS_API_KEY` in the Render dashboard. It is marked `sync: false`, so the key is not committed.
4. Render runs `pip install uv && uv sync` and starts the Uvicorn web service.

The free Render instance has no GPU, so `llama-server` telemetry reports `offline` and triage uses the deterministic heuristic path. That is intentional: judges can test ingestion, radar, and the dashboard without a local model. The audio player falls back to browser speech when ElevenLabs is not configured.

---

## License

MIT
