"""
VoiceKit -- FastAPI server with real-time voice AI pipeline.

Routes:
    POST /voice          -> Webhook that returns TwiML to start a bidirectional stream.
    WS   /media-stream   -> WebSocket endpoint for the voice pipeline.
    GET  /health         -> Health check.

Run with:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse

from backend.telephony.base import TelephonyProvider
from backend.stt.base import STTProvider
from backend.llm.base import LLMProvider
from backend.tts.base import TTSProvider
from backend.pipeline import VoicePipeline

# ── Configuration ────────────────────────────────────────────────────
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SERVER_PORT = int(os.getenv("PORT", "8000"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Provider configuration from environment ──────────────────────────
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")

# ── FastAPI application ──────────────────────────────────────────────
app = FastAPI(title="VoiceKit", version="0.2.0")


@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


@app.api_route("/voice", methods=["GET", "POST"])
async def voice_webhook(request: Request):
    """Twilio voice webhook -- returns TwiML that opens a bidirectional media stream.

    Twilio calls this URL when a call arrives (inbound or outbound).
    We respond with TwiML that instructs Twilio to connect a
    WebSocket media stream to our /media-stream endpoint.
    """
    # Determine the WebSocket URL based on the request's host header.
    # In production this will be the ngrok / public hostname.
    host = request.headers.get("host", "localhost:8000")

    # Use wss:// when behind TLS (ngrok, etc.), ws:// for plain localhost
    scheme = "wss" if request.url.scheme == "https" or "ngrok" in host else "ws"
    ws_url = f"{scheme}://{host}/media-stream"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Pause length="1" />'
        "<Connect>"
        f'<Stream url="{ws_url}" />'
        "</Connect>"
        "</Response>"
    )

    logger.info("Incoming call -- returning TwiML with stream URL: %s", ws_url)
    return PlainTextResponse(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """Bidirectional WebSocket endpoint for the voice pipeline.

    When Twilio connects, we instantiate all four pipeline providers
    and run the full STT -> LLM -> TTS loop for this call.
    """
    # Create providers for this call session
    telephony = TelephonyProvider.from_twilio()
    stt = STTProvider.from_deepgram(api_key=DEEPGRAM_API_KEY)
    llm = LLMProvider.from_groq(api_key=GROQ_API_KEY)
    tts = TTSProvider.from_elevenlabs(
        api_key=ELEVENLABS_API_KEY,
        voice_id=ELEVENLABS_VOICE_ID,
    )

    # Connect telephony (accepts the WebSocket)
    await telephony.connect(websocket)

    # Build and run the pipeline
    pipeline = VoicePipeline(
        telephony=telephony,
        stt=stt,
        llm=llm,
        tts=tts,
    )

    try:
        await pipeline.run()
    finally:
        logger.info("Media stream connection closed")
