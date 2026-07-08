"""
Local runner for testing VoiceKit without Twilio or ngrok.

Uses your local microphone and speakers to stream audio through
the AI pipeline. Useful for testing when Twilio credits are exhausted.
"""

import asyncio
import logging
import os
import sys

# Add the project root to the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

from backend.llm.openai_provider import OpenAILLM
from backend.pipeline import VoicePipeline
from backend.prompts import DEFAULT_SYSTEM_PROMPT
from backend.rag.engine import RAGEngine
from backend.stt.deepgram_provider import DeepgramSTT
from backend.tts.elevenlabs_provider import ElevenLabsTTS
from testing.local_mic.local_provider import LocalAudioProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()

async def main():
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")

    if not all([DEEPGRAM_API_KEY, OPENAI_API_KEY, ELEVENLABS_API_KEY]):
        logger.error("Missing required API keys in .env file!")
        return

    # Initialize RAG Engine
    logger.info("Initializing RAG engine...")
    rag_engine = RAGEngine(api_key=OPENAI_API_KEY)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    kb_path = os.path.join(base_dir, "business", "knowledge_base")
    await rag_engine.initialize(kb_path, chunk_size=1000, chunk_overlap=200)

    # Load business prompt
    prompt_path = os.path.join(base_dir, "business", "prompt.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            business_prompt = f.read().strip()
    except Exception:
        business_prompt = ""
    
    combined_prompt = f"{business_prompt}\n\n{DEFAULT_SYSTEM_PROMPT}" if business_prompt else DEFAULT_SYSTEM_PROMPT

    # Initialize Providers
    telephony = LocalAudioProvider()
    stt = DeepgramSTT(api_key=DEEPGRAM_API_KEY)
    llm = OpenAILLM(api_key=OPENAI_API_KEY, system_prompt=combined_prompt)
    tts = ElevenLabsTTS(api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE_ID)

    pipeline = VoicePipeline(
        telephony=telephony,
        stt=stt,
        llm=llm,
        tts=tts,
        rag=rag_engine,
    )
    
    logger.info("Starting Local Voice Pipeline...")
    logger.info("Press Ctrl+C to stop.")
    
    await telephony.connect()
    
    try:
        await pipeline.run()
    except asyncio.CancelledError:
        pass
    finally:
        await telephony.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
