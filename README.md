# BridgeAI – Autonomous Multi-Tier AI Email & Workflow Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19.0-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)](https://neon.tech/)
[![Google GenAI](https://img.shields.io/badge/Google%20GenAI-Gemini%20Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Deploy: Vercel](https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel&logoColor=white)](https://bridgeai-email-agent.vercel.app)

BridgeAI is a private, intelligent email and workflow assistant built on **FastAPI**, **React 19**, **Google GenAI SDK (`gemini-3.8-flash`)**, and **Neon PostgreSQL + `pgvector`**. It connects securely to Gmail via OAuth 2.0 PKCE, executes deterministic tool calling for mailbox triage and natural language queries, and maintains persistent semantic memory across sessions without hardcoded logic.

---

## Live Demo & Repositories

- **Live Production App**: [https://bridgeai-email-agent.vercel.app](https://bridgeai-email-agent.vercel.app)
- **GitHub Repository**: [https://github.com/rishikeshkharade/Email-Agent](https://github.com/rishikeshkharade/Email-Agent)

---

## Key Highlights & Capabilities

- 🤖 **Autonomous Function Calling & Safe Reasoning**: Direct integration with Google GenAI SDK using strictly typed tool declarations (`filter_unread_emails`, `search_emails`, `review_email`). Enforces a strict budget limit (`max_tool_calls = 5`) and operates with **strictly read-only permissions** (no destructive email edits, deletes, or unsolicited sending).
- 🧠 **Dual-Tier Hybrid Memory Architecture**:
  - **Tier 1 (Session Tab Cache)**: Client-side `sessionStorage` state preservation prevents chat loss on accidental browser refreshes (`Ctrl+R`), with immediate memory wiping on application/browser exit or via the `[ + New chat ]` button.
  - **Tier 2 (Semantic Long-Term Vector Memory)**: Integrated **PostgreSQL with `pgvector`** (Neon Serverless). Generates **768-dimensional embeddings** via Gemini (`gemini-embedding-001`) to automatically recall cross-session user preferences (e.g. formatting preferences, frequent projects, topic context) using cosine similarity search.
- ⚡ **Sub-50ms Fast-Path & Performance Engineering**:
  - Pure conversational greetings (e.g. *"Hello"*, *"Good morning"*) and courtesies bypass external LLM API latency completely via a regex fast-path router (`<50ms` response time).
  - Asynchronous non-blocking memory persistence (`ThreadPoolExecutor`) ensures zero user latency on active chat turns.
  - Zero-token 4-stage heuristic email triage pipeline for instant client-side card summarization.
- 🔒 **Enterprise-Grade Authentication & Security**:
  - Multi-user Google OAuth 2.0 PKCE flow with HTTP-only, SameSite Secure session cookies.
  - Automatic proactive background token refresh prevents workflow interruption on expired sessions.
- 🎨 **Modern Interactive UI**:
  - Single-page interface built with **React 19, TypeScript, and Vite**.
  - Dynamic contextual loading indicators (`"Searching your mailbox..."`, `"Reviewing emails..."`), interactive email cards with one-click **"Join Meeting"** shortcuts, and responsive sticky navigation.

---

## Architecture & Flow

```mermaid
flowchart TD
    User([User / Browser]) <--> ReactUI[React 19 UI + sessionStorage]
    ReactUI <--> FastAPI[FastAPI Backend /agent/chat]

    subgraph FastPathRouter [Latency Optimization]
        FastAPI --> FastPath{Conversational Greeting?}
        FastPath -- Yes (<50ms) --> FastResponse[Instant Greeting Response]
    end

    FastPath -- No --> MemoryRetrieval[Neon PostgreSQL pgvector<br/>Cosine Similarity Search]
    MemoryRetrieval --> PromptGen[Dynamic Prompt Engine<br/>Temporal UTC Context + Recalled Memory]
    PromptGen --> Gemini[Google GenAI SDK<br/>gemini-3.8-flash]

    Gemini <--> FunctionCalling{Autonomous Tool Call?}
    FunctionCalling -- Yes --> GmailAPI[Gmail API Read-Only Tools]
    GmailAPI --> Gemini
    FunctionCalling -- No --> FinalResp[Structured Chat Response + Cards]

    FinalResp --> AsyncWorker[Background Worker<br/>ThreadPoolExecutor]
    AsyncWorker --> NeonDB[(Neon PostgreSQL<br/>chat_memories vector(768))]
    FinalResp --> ReactUI
```

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend & API** | Python 3.12, FastAPI, Pydantic v2, Pydantic-Settings, Uvicorn |
| **LLM & AI Orchestration** | Google GenAI SDK (`google-genai`), Gemini 3.8 Flash, `gemini-embedding-001` |
| **Database & Vector RAG** | Neon Serverless PostgreSQL 18, `pgvector`, `psycopg2-binary` |
| **Frontend** | React 19, TypeScript, Vite, CSS3 Variables, Phosphor/Lucide Icons |
| **Integrations & Security** | Google OAuth 2.0 PKCE, Gmail API, HTTP-only Secure Cookies |
| **Testing & Quality** | Pytest, 66 automated unit/integration tests, 100% clean passes |
| **Deployment** | Vercel (Production Web App), Neon.tech (Managed Cloud Database) |

---

## Project Structure

```text
bridgeai-email-agent/
├── app/
│   ├── api/routes/            # API endpoints (chat, auth, memory, emails)
│   ├── core/                  # Configuration, logging, session cookie management
│   ├── integrations/          # Gmail API provider & OAuth token handling
│   ├── prompts/               # Evergreen system prompts & temporal context calculators
│   ├── schemas/               # Pydantic models for request/response validation
│   ├── services/              # AI service, email tools, memory service, heuristics
│   └── static/react-ui/       # Production compiled React frontend assets
├── frontend/                  # React 19 + TypeScript frontend source code
│   ├── src/components/        # Navbar, MessageList, EmailCard, PromptBar
│   ├── src/styles.css         # Modern dark-mode styling
│   └── package.json
├── tests/                     # 66 comprehensive automated pytest test suites
│   ├── agent/                 # Chat service & tool-calling flow tests
│   ├── api/                   # FastAPI route integration tests
│   ├── integration/           # Gmail API & OAuth tests
│   └── unit/                  # Config, signals, summaries, memory tests
├── .env.example               # Environment variables template
├── requirements.txt           # Python backend dependencies
├── vercel.json                # Vercel serverless deployment configuration
└── README.md
```

---

## Getting Started Locally

### 1. Prerequisites
- **Python 3.11+** (Python 3.12 recommended)
- **Node.js 18+** & **npm** (for building frontend)
- A **Google Cloud Console Project** with Gmail API enabled and OAuth credentials configured.
- A free **Neon.tech** PostgreSQL database (or local PostgreSQL with `pgvector`).

### 2. Clone the Repository
```bash
git clone https://github.com/rishikeshkharade/Email-Agent.git
cd Email-Agent
```

### 3. Backend Setup
Create and activate a virtual environment:
```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies:
pip install -r requirements.txt
```

### 4. Configuration (`.env`)
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```
Key configuration items:
```ini
ENVIRONMENT=development
LOG_LEVEL=INFO
APP_PORT=8001
GEMINI_API_KEY=your_google_ai_studio_api_key
GEMINI_MODEL=gemini-3.8-flash

# Google OAuth Credentials (for local desktop OAuth flow):
OAUTH_CREDENTIALS_PATH=credentials/credentials.json
OAUTH_TOKEN_PATH=token.json

# Neon PostgreSQL + pgvector Connection:
DATABASE_URL=postgresql://user:password@ep-xxxx.neon.tech/neondb?sslmode=require
```

### 5. Frontend Build (Optional if modifying UI)
```bash
cd frontend
npm install
npm run build
cd ..
```
The compiled output is automatically bundled into `app/static/react-ui/` for FastAPI to serve.

### 6. Run the Application
```bash
uvicorn app.main:app --port 8001 --reload
```
Open your browser at `http://localhost:8001`.

---

## Running Automated Tests

Run the full pytest suite (66 tests covering tools, providers, temporal arithmetic, and vector memory):
```bash
pytest tests/ -v
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
