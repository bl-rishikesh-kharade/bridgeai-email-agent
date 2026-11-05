# BridgeAI Email Agent

BridgeAI is a local, single-user Gmail assistant. It connects to Gmail using the user's own Google OAuth client and stores the authorization token on that computer. Gemini handles natural-language chat and email review. The application does not persist chat history.

## Current scope

- Connect one Gmail account through the **Connect Google** screen.
- Chat in natural language to list, search, retrieve, summarize, or ask about email.
- Use the **Unread important** shortcut to fetch messages Gmail labels both Important and Unread. If there are more than 100 unread important emails, the shortcut restricts results to the last 48 hours.
- Open an email from the result card using **View in Gmail**.
- Read-only Gmail access. No task creation, calendar integration, or other mail providers are enabled in this version.

## Request flow

```text
React chat → FastAPI route → ChatService → Gemini chooses a declared email tool
                                             ↓
                                    Gmail provider → Gmail API
                                             ↓
                              results returned to the chat UI
```

The **Unread important** button calls the Gmail label filter directly. Other chat requests go to Gemini, which can answer or ask the backend to run a validated read-only email tool. There is no LangGraph or LangChain in this version. The backend uses a temporary request context to pass data between Python functions; it is discarded after each request and is not conversation memory.

## Setup & Documentation

- [Setup Guide](docs/SETUP.md) for local installation, Google Cloud credentials, and configuration.
- [Architecture & Design](docs/ARCHITECTURE.md) for full-stack architecture, request flows, and signal engine.
- [Security & Codebase Audit Report](docs/AUDIT_REPORT.md) for verified audit findings and fixes.

The frontend source is in `frontend/` and the built interface ships in `app/static/react-ui/`. Node.js is needed only to edit and rebuild the interface.

## Local secrets and logs

`.env`, `credentials/credentials.json`, and `token.json` are local private files and should never be committed or shared. The app writes operational logs to the terminal and a rotating file. Set `LOG_FILE_PATH` in `.env` to choose a custom log path.

The application can answer about the connected Gmail mailbox only. It does not answer general knowledge questions unless Gemini can answer without mailbox data. Outlook, Yahoo, hosted Vercel access, and persistent chat history are outside this version's scope.
