# AI Email Agent - Technical Specification & Requirements

## Architecture & Overview
- **Application**: BridgeAI Email Agent
- **Backend**: FastAPI (Python 3.12)
- **Frontend**: React 19 + TypeScript (Vite)
- **Email Provider**: Google Gmail API (OAuth 2.0 Desktop/Web Installed Flow)
- **Model / Inference**: Google GenAI (Gemini 3.5-Flash-Lite with automated fallback to Gemini 3.1-Flash-Lite)

---

## Project Plan

### Week 1
- Finalize agentic framework and core service interfaces.

### Week 2
- Google OAuth 2.0 Login / Re-authentication flow.
- Interactive local Chat Workspace.
- Gmail tools: list, search, retrieve, unread/important filtering.

### Week 3 (Current)
- **Signals & Deterministic Priority Engine**:
  - Separate user-configurable JSON file: `config/signals.json`.
  - Priority levels: `Critical`, `High`, `Medium`, `Low`.
  - Deterministic priority ranking (Critical sorted to the top).
  - Explicit user name mention detection in email body and subject.
- **Hybrid Importance Strategy**:
  - `signals`: Evaluates unread emails strictly against custom keyword and sender rules.
  - `gmail`: Relies on Gmail's native `label:IMPORTANT`.
  - `hybrid` (Default): Evaluates custom signals first; falls back to Gmail `IMPORTANT` if no custom signals match.
- **Clean Chat Interface & Output**:
  - Suppressed duplicate numbered text lists (`1. ... 2. ...`) inside the chat bubble.
  - Visual interactive cards display:
    - Priority Badge (`Critical`, `High`, `Medium`, `Low`)
    - Subject
    - From & To addresses
    - Body snippet preview
    - "View in Gmail" direct link button
- **Multi-Turn Conversational Memory**:
  - Client-buffered rolling conversational memory without external database or Redis dependencies.
- **Resilience & Fault Tolerance**:
  - Automatic retry with exponential backoff on transient HTTP 503 / 429 server demand spikes.
  - Multi-model redundancy and fallback across active free-tier models.
  - Development live auto-reload enabled.
