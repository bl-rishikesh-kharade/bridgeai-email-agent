# BridgeAI Email Agent architecture

## Startup

```text
python run.py
  → app/cli.py starts Uvicorn on 127.0.0.1
  → app/main.py creates the Gmail and OAuth services
  → FastAPI registers auth, chat, and health routes
  → FastAPI serves the built React interface
```

## Connect Google

```text
Connect Google button
  → POST /auth/connect
  → Google OAuth Desktop app flow opens in the browser
  → authorization is saved to local token.json
  → UI shows the email workspace
```

The saved token is reused on later launches and refreshed when needed. The user can remove `token.json` to disconnect and authorize again.

## Chat request

```text
User message
  → React sends POST /agent/chat
  → app/api/routes/agent.py validates the request
  → app/services/chat_service.py calls Gemini with allowed email tools
  → Gemini answers or requests a read-only tool
  → app/services/email_tools.py validates and runs that tool
  → app/integrations/email/gmail_provider.py calls Gmail API
  → chat response and email cards return to React
```

The **Unread important** button sends its filter ID to the chat route. Python directly asks Gmail for messages carrying both the `UNREAD` and `IMPORTANT` system labels. If more than 100 messages match, it adds Gmail's `newer_than:2d` constraint. Gemini does not decide whether Gmail marked an email important.

Other chat messages go to Gemini, which may answer directly or choose a declared tool such as list, search, retrieve, or review email. Python checks tool arguments and enforces a maximum number of tool calls. Gmail access is read-only.

`ChatService` passes a temporary `request_context` dictionary between these ordinary Python functions while it handles one request. It is discarded when that request finishes. It is not a LangGraph state, a user session, or saved conversation memory.

Chat history is not persisted. The current page holds messages in browser memory; reloading or closing it clears them. A new request has no server-side conversation/thread memory, so ask follow-up questions with enough email context or make a new request.

## Main files

| File or folder | Responsibility |
|---|---|
| `run.py`, `app/cli.py` | Start the local server. |
| `app/main.py` | Create services and register routes. |
| `app/api/routes/auth.py` | Report connection status and run Google authorization. |
| `app/api/routes/agent.py` | Accept chat requests and format the response. |
| `app/services/chat_service.py` | Coordinate Gemini calls and tool execution. |
| `app/services/email_tools.py` | Declare tools, validate arguments, and invoke email operations. |
| `app/services/ai_service.py` | Call Gemini for chat and email review. |
| `app/integrations/google/oauth.py` | Load, refresh, connect, and save local Google credentials. |
| `app/integrations/email/gmail_provider.py` | Read and search Gmail, and create Gmail links. |
| `app/core/config.py`, `app/core/logger.py` | Read settings and record operational logs. |
| `frontend/src/` | React application source. |
| `app/static/react-ui/` | Built React files served by FastAPI. |

This version uses direct Gemini SDK calls and explicit Python control flow. It does not use LangGraph or LangChain. Tasks, Calendar, other mailbox providers, Vercel hosting, and persistent chat history are outside the current active app flow.
