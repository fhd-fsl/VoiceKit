# VoiceKit Browser Softphone

This is a standalone test tool used test VoiceKit. It allows you to simulate an incoming voice call to the VoiceKit server directly from your browser.

## Setup

1. Create a Python virtual environment and install the dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install fastapi uvicorn twilio python-dotenv
   ```
2. The softphone requires a `.env` file in this directory with the following credentials:
   ```
   TWILIO_ACCOUNT_SID=...
   TWILIO_API_KEY=...
   TWILIO_API_SECRET=...
   TWILIO_TWIML_APP_SID=...
   TWILIO_CALLER_ID=...
   ```

## How it works

When you click "Call", the softphone uses the `@twilio/voice-sdk` to connect to your Twilio TwiML App.
Your Twilio TwiML App is configured to point its Voice Webhook directly to the `VoiceKit` server's main `/voice` endpoint.

This means you do **not** need to expose this softphone to the internet using ngrok. Only the main VoiceKit server needs to be exposed via ngrok.

## Running the Softphone

1. Start the standalone softphone server on a different port than the main VoiceKit server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8001
   ```
2. Open the UI in your browser:
   [http://localhost:8001/static/index.html](http://localhost:8001/static/index.html)
3. Ensure the main VoiceKit server is running on port `8000` (with its ngrok tunnel active).
4. Click **Call**. You will connect to the VoiceKit WebSocket and hear your audio echoed back.
