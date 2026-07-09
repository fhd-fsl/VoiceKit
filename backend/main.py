"""
VoiceKit -- FastAPI server with real-time voice AI pipeline.

Routes:
    POST /voice          -> Webhook that returns TwiML to start a bidirectional stream.
    WS   /media-stream   -> WebSocket endpoint for the voice pipeline.
    GET  /health         -> Health check.

Run with:
    python run.py
"""

import logging
import os
import importlib

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse

from backend.telephony.base import TelephonyProvider
from backend.stt.base import STTProvider
from backend.llm.base import LLMProvider
from backend.tts.base import TTSProvider
from backend.pipeline.coordinator import VoicePipeline
from backend.rag.engine import RAGEngine
from backend.utils.config import load_config

# ── Configuration ────────────────────────────────────────────────────
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("backend").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Load the app configuration
config = load_config()

# ── Global API Keys from environment ─────────────────────────────────
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ── Global RAG Engine ────────────────────────────────────────────────
rag_engine = RAGEngine(api_key=OPENAI_API_KEY)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize RAG on startup using config parameters
    kb_path = config.rag.knowledge_base_dir
    # Ensure relative paths are resolved from the project root
    if not os.path.isabs(kb_path):
        kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), kb_path)
        
    await rag_engine.initialize(
        docs_dir=kb_path, 
        chunk_size=config.rag.chunk_size, 
        chunk_overlap=config.rag.chunk_overlap
    )
    yield

# ── FastAPI application ──────────────────────────────────────────────
app = FastAPI(title="VoiceKit", version="0.3.0", lifespan=lifespan)


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
    host = request.headers.get("host", "localhost:" + str(config.telephony.twilio.port))

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
    # 1. Telephony Provider
    if config.telephony.provider == "twilio":
        telephony = TelephonyProvider.from_twilio()
    else:
        # Fallback or local testing logic could go here
        telephony = TelephonyProvider.from_twilio()

    # 2. System Prompt
    business_prompt = config.agent.prompt

    from backend.prompts import DEFAULT_SYSTEM_PROMPT
    combined_prompt = f"{business_prompt}\n\n{DEFAULT_SYSTEM_PROMPT}" if business_prompt else DEFAULT_SYSTEM_PROMPT

    # 3. STT Provider
    if config.stt.provider == "deepgram":
        stt_conf = config.stt.deepgram
        stt = STTProvider.from_deepgram(
            api_key=DEEPGRAM_API_KEY,
            model=stt_conf.model if stt_conf else "nova-3",
            language=stt_conf.language if stt_conf else "en-US"
        )
    else:
        stt = STTProvider.from_deepgram(api_key=DEEPGRAM_API_KEY)

    # 4. LLM Provider
    if config.llm.provider == "groq":
        llm_conf = config.llm.groq
        llm = LLMProvider.from_groq(
            api_key=GROQ_API_KEY, 
            system_prompt=combined_prompt,
            model=llm_conf.model if llm_conf else "llama-3.1-8b-instant",
            temperature=llm_conf.temperature if llm_conf else 0.2
        )
    else:
        llm_conf = config.llm.openai
        llm = LLMProvider.from_openai(
            api_key=OPENAI_API_KEY, 
            system_prompt=combined_prompt,
            model=llm_conf.model if llm_conf else "gpt-4o-mini",
            temperature=llm_conf.temperature if llm_conf else 0.2
        )

    # 5. TTS Provider
    if config.tts.provider == "elevenlabs":
        tts_conf = config.tts.elevenlabs
        tts = TTSProvider.from_elevenlabs(
            api_key=ELEVENLABS_API_KEY,
            voice_id=tts_conf.voice_id if tts_conf else "JBFqnCBsd6RMkjVDRZzb"
        )
    else:
        tts = TTSProvider.from_elevenlabs(api_key=ELEVENLABS_API_KEY, voice_id="JBFqnCBsd6RMkjVDRZzb")

    # Connect telephony (accepts the WebSocket)
    await telephony.connect(websocket)

    # Build and run the pipeline
    pipeline = VoicePipeline(
        telephony=telephony,
        stt=stt,
        llm=llm,
        tts=tts,
        rag=rag_engine,
    )

    try:
        await pipeline.run()
    finally:
        logger.info("Media stream connection closed")
