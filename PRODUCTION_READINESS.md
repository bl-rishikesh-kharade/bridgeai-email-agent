# Local release checklist

## Current product scope

BridgeAI currently runs locally for one user and connects to that user's Gmail and Gemini API key. OAuth is a Google Desktop app flow; the token remains on that computer. The supported mailbox integration is Gmail read-only. The active UI contains the Google connect screen, chat, and the Unread important shortcut. Chat history is not persisted.

## Before sharing a customer build

| Priority | Work | Reason |
|---|---|---|
| Required | Verify a clean Windows and macOS setup, Google authorization, token refresh/revocation, Gmail search, and the unread-important cutoff with dedicated test accounts. | A frontend build or mocked provider behavior does not verify real customer configuration. |
| Required | Package and test a signed installer that includes the built React UI and documents upgrade, disconnect, and uninstall. | A project ZIP is a developer handoff, not a polished consumer installer. |
| Required | Review OAuth consent-screen publishing/verification requirements and clearly describe which email data is sent to Gemini. | Google controls account authorization, and email content is sent to the configured model for AI requests. |
| Recommended | Store the Gemini key and OAuth refresh token in the operating system credential store. | Current development setup uses local `.env` and `token.json` files. |
| Recommended | Pin dependencies and add release automation for frontend builds, dependency checks, and packaging. | Reproducible builds reduce version drift and manual release errors. |
| Recommended | Keep the server bound to loopback and document local logs and recovery steps. | The app has no web sign-in or multi-user access boundary. |

Do not expose this local server as a public or office-shared web service. Vercel hosting, account allow-lists, multi-user storage, persistent chat history, task/calendar workflows, and non-Gmail providers are not part of this release scope.
