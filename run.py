import os
import sys
import subprocess
import asyncio
import logging
from pyngrok import ngrok
from twilio.rest import Client
from dotenv import load_dotenv
from backend.utils.config import load_config

def start_twilio_server(config):
    port = config.telephony.twilio.port
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    phone_number = config.telephony.twilio.phone_number

    if not all([account_sid, auth_token, phone_number]):
        print("Error: Missing essential Twilio environment variables or phone number in config.yaml.")
        sys.exit(1)

    # 1. Start Ngrok
    print(f"Starting ngrok tunnel on port {port}...")
    ngrok_auth = os.getenv("NGROK_AUTHTOKEN")
    if ngrok_auth:
        ngrok.set_auth_token(ngrok_auth)
    
    public_url = ngrok.connect(port).public_url
    print(f"Ngrok tunnel established at: {public_url}")

    # 2. Update Twilio Webhook
    print(f"Updating Twilio Phone Number ({phone_number}) webhook...")
    client = Client(account_sid, auth_token)
    
    numbers = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
    if not numbers:
        print(f"Error: Could not find phone number {phone_number} on your Twilio account.")
        ngrok.kill()
        sys.exit(1)

    twilio_number = numbers[0]
    webhook_url = f"{public_url}/voice"
    
    twilio_number.update(voice_url=webhook_url, trunk_sid="")
    print(f"Webhook updated to: {webhook_url}")

    # 3. Start Uvicorn Server
    print("Starting FastAPI Server...")
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(port)])
    except KeyboardInterrupt:
        print("\nStopping VoiceKit...")
    finally:
        print("Cleaning up ngrok tunnel...")
        ngrok.kill()

async def run_local_pipeline(config):
    print("Starting Local Microphone Pipeline...")
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("LocalPipeline")
    logger.setLevel(logging.INFO)
    logging.getLogger("backend").setLevel(logging.INFO)
    
    from backend.pipeline.coordinator import VoicePipeline
    from backend.stt.base import STTProvider
    from backend.llm.base import LLMProvider
    from backend.tts.base import TTSProvider
    from backend.rag.engine import RAGEngine
    from testing.local_mic.local_provider import LocalAudioProvider

    # Load API Keys
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

    # Init RAG
    rag_engine = RAGEngine(api_key=OPENAI_API_KEY)
    kb_path = config.rag.knowledge_base_dir
    if not os.path.isabs(kb_path):
        kb_path = os.path.abspath(kb_path)
    await rag_engine.initialize(kb_path, chunk_size=config.rag.chunk_size, chunk_overlap=config.rag.chunk_overlap)

    # Prompt
    business_prompt = config.agent.prompt
    from backend.prompts import DEFAULT_SYSTEM_PROMPT
    combined_prompt = f"{business_prompt}\n\n{DEFAULT_SYSTEM_PROMPT}" if business_prompt else DEFAULT_SYSTEM_PROMPT

    # Providers
    telephony = LocalAudioProvider()
    
    if config.stt.provider == "deepgram":
        stt = STTProvider.from_deepgram(
            api_key=DEEPGRAM_API_KEY, model=config.stt.deepgram.model, language=config.stt.deepgram.language
        )
    else:
        stt = STTProvider.from_deepgram(api_key=DEEPGRAM_API_KEY)

    if config.llm.provider == "groq":
        llm = LLMProvider.from_groq(
            api_key=GROQ_API_KEY, system_prompt=combined_prompt, model=config.llm.groq.model, temperature=config.llm.groq.temperature
        )
    else:
        llm = LLMProvider.from_openai(
            api_key=OPENAI_API_KEY, system_prompt=combined_prompt, model=config.llm.openai.model, temperature=config.llm.openai.temperature
        )

    if config.tts.provider == "elevenlabs":
        tts = TTSProvider.from_elevenlabs(
            api_key=ELEVENLABS_API_KEY, voice_id=config.tts.elevenlabs.voice_id
        )
    else:
        tts = TTSProvider.from_elevenlabs(api_key=ELEVENLABS_API_KEY, voice_id="JBFqnCBsd6RMkjVDRZzb")

    pipeline = VoicePipeline(telephony=telephony, stt=stt, llm=llm, tts=tts, rag=rag_engine)
    
    logger.info("Press Ctrl+C to stop.")
    await telephony.connect()
    try:
        await pipeline.run()
    except asyncio.CancelledError:
        pass
    finally:
        await telephony.close()

def main():
    print("Starting VoiceKit Config Launcher...")
    load_dotenv()
    config = load_config()
    
    if config.telephony.provider == "twilio":
        start_twilio_server(config)
    else:
        try:
            asyncio.run(run_local_pipeline(config))
        except KeyboardInterrupt:
            print("Shutting down...")

if __name__ == "__main__":
    main()
