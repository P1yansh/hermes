# 🏛️ Hermes Agent & Skill Guidelines

This document governs agent behavior, engineering standards, and workflow disciplines for **Hermes**. Every AI agent, automated session, and pair-programming turn must adhere to these protocols.

---

## 1. Curated Agent Personas & Specializations

| Agent Persona | Focus Area | Operational Mandate |
| :--- | :--- | :--- |
| **`tdd-architect`** | Test-Driven Development & Verification | Enforce non-interactive test suites (`uv run pytest`). Every new connector, radar calculation, prompt pipeline, and API route must have 100% automated test coverage before committing. |
| **`backend-architect`** | Clean Architecture & Async Safety | Design async FastAPI endpoints, Pydantic v2 schemas (`model_dump()`, no v1 `.dict()`), dependency injection, and clean strategy pattern separation (`MockConnector` vs `GoogleLiveConnector`). Zero blocking synchronous calls inside route handlers. |
| **`llm-prompt-engineer`** | Open-Weight Gemma 3 Optimization | Optimize constrained JSON extraction and few-shot system prompts for local `llama.cpp` inference on Gemma 3 4B. Always provide robust heuristic fallback logic for offline/CI resilience. |
| **`ui-designer`** | Minimalist Student Dashboard | Design glassmorphic, high-contrast dark mode interfaces with color-coded urgency radar bands (🔴 Panic, 🟡 Imminent, 🟢 Upcoming) and audio playback controls. |
| **`devchallenge-strategist`** | Hacktoberfest DEV Submission | Continuously optimize for DEV Community judging criteria: Writing Quality (weighted most heavily), "Why Open Innovation Matters", and multi-partner category alignment (Gemma, Render, ElevenLabs, .tech domain). |

---

## 2. Curated Skills & Technical Disciplines

* **`testing-patterns`**: Mock fixtures, asynchronous client testing with `httpx.AsyncClient` + `ASGITransport`, edge-case deadline assertions (negative vs imminent hours).
* **`fastapi-clean-architecture`**: Routers decoupled from business logic; services decoupled from persistence; zero circular imports; strict type safety.
* **`uv-project-management`**: Utilizing `pyproject.toml` and `uv` lockfiles for sub-second installs and reproducible builds on Render.
* **`liquid-glass-ui`**: Minimalist, clean visual layouts with fluid transitions, audio waves, and glanceable deadline tickers.
* **`git-hygiene`**: Conventional commits, zero secret leakage, maintaining total independence between Athena core and the `projects/hermes` repository.

---

## 3. Active Conversation Protocols (Strictly Enforced)

1. **Test-Driven Discipline (`tdd-architect`)**:
   - Run non-interactive tests (`uv run pytest -v`) after every logic modification.
   - Never consider a feature complete without passing unit/integration tests.
2. **Pydantic v2 & Async Safety (`backend-architect`)**:
   - Strict avoidance of deprecated Pydantic v1 methods (use `.model_dump()`, timezone-aware `datetime.now(timezone.utc)`).
   - Use `async/await` and non-blocking HTTP clients (`httpx.AsyncClient`).
3. **Dual-Path Heuristic Fallbacks (`llm-prompt-engineer`)**:
   - Every agent interaction with local `llama-server` (Gemma) or ElevenLabs TTS must include an immediate deterministic fallback so tests and offline demos never crash.
4. **Architectural Boundary Isolation**:
   - The root Athena workspace remains clean and unmodified. All project code, tests, and configurations reside exclusively within `projects/hermes`.
5. **Hackathon Alignment (`devchallenge-strategist`)**:
   - Every design decision must directly support the Hacktoberfest Week 3 theme (*"Slow and Steady" / Rewards Laziness*) and partner prize criteria (Gemma, Render, ElevenLabs, .tech).
