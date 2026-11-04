# BridgeAI Email Agent setup

BridgeAI runs on your computer and connects to one Gmail account. You provide the Google OAuth client and Gemini API key for your installation. The app requests read-only Gmail access. It does not save chat history.

## Before you start

- Python 3.12 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- A Google Cloud OAuth **Desktop app** client JSON file with the Gmail API enabled

## Windows

1. Install Python 3.12 or newer and enable **Add Python to PATH** in the installer. Extract the project ZIP to a folder such as `C:\BridgeAI`.
2. Open PowerShell in the extracted `bridgeai-email-agent` folder and create the virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

3. In Google Cloud Console, create or select a project, enable **Gmail API**, configure Google Auth Platform for your account, and create a **Desktop app** OAuth client. Download its JSON file. If Google's OAuth app is in Testing, add your account as a test user.
4. Create the local configuration and credentials folder:

   ```powershell
   Copy-Item .env.example .env
   New-Item -ItemType Directory -Force credentials
   ```

5. Put the downloaded OAuth JSON at `credentials\credentials.json`. Edit `.env` and set `GEMINI_API_KEY` to your key. Keep `.env`, the OAuth JSON, and the generated `token.json` private; they are ignored by Git.
6. Start the app:

   ```powershell
   python run.py
   ```

7. Open `http://127.0.0.1:8000`, select **Connect Google**, sign in to the Gmail account you want to use, and approve read-only Gmail access. Google opens in your browser; after authorization, BridgeAI saves the token locally and opens the chat workspace.

## macOS

1. Install Python 3.12 or newer. Extract the ZIP, then open Terminal in the extracted `bridgeai-email-agent` folder.
2. Create the virtual environment and install requirements:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

3. In Google Cloud Console, create or select a project, enable **Gmail API**, configure Google Auth Platform for your account, and create a **Desktop app** OAuth client. Download its JSON file. If Google's OAuth app is in Testing, add your account as a test user.
4. Create local configuration and credentials folders:

   ```bash
   cp .env.example .env
   mkdir -p credentials
   ```

5. Put the downloaded OAuth JSON at `credentials/credentials.json`. Edit `.env` and set `GEMINI_API_KEY` to your key. Keep `.env`, the OAuth JSON, and the generated `token.json` private; they are ignored by Git.
6. Start the app:

   ```bash
   python run.py
   ```

7. Open `http://127.0.0.1:8000`, select **Connect Google**, sign in to the Gmail account you want to use, and approve read-only Gmail access. Google opens in your browser; after authorization, BridgeAI saves the token locally and opens the chat workspace.

## Using the chat

- Select **Unread important** to list mail that Gmail marks both **Important** and **Unread**. If there are more than 100 unread important messages, results are restricted to those from the last 48 hours.
- Type a request to list or search Gmail, or ask Gemini to review a selected email. Chat history is kept only in the current page and is cleared when you reload or close it.
- Email results show the subject, sender, and date. **View in Gmail** opens that message in the connected account.

The built-in email provider currently supports Gmail. Outlook, Yahoo, and other providers are not configured in this version. The interface source is React; Node.js is needed only if you plan to edit and rebuild it. See [README.md](README.md) for project details.

To disconnect or authorize a different Google account, stop BridgeAI, remove the local `token.json`, start the app again, and select **Connect Google**.
On later launches, a valid saved token is reused, so the chat opens without repeating consent. Google authorization can still require reconnection if revoked or expired under the OAuth app's publishing/testing settings.
