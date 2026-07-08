# VoiceKit

A real-time voice AI backend that connects phone calls to a streaming AI pipeline via Twilio Media Streams. Inbound calls flow through a modular pipeline: **Telephony -> STT -> LLM -> TTS -> Telephony**, with each layer swappable via a provider abstraction.

## Architecture

```
┌──────────┐  PSTN   ┌──────────┐  POST /voice   ┌──────────────────────┐
│  Caller  │────────>│  Twilio  │───────────────>│  FastAPI Server      │
│  Phone   │         │  Cloud   │                │  (returns TwiML)     │
└──────────┘         └────┬─────┘                └──────────────────────┘
                          │                               │
                          │  wss:// /media-stream          │
                          ▼                               │
                   ┌──────────────┐<──────────────────────┘
                   │  Voice       │
                   │  Pipeline    │
                   │              │
                   │  Telephony ──> STT ──> LLM ──> TTS ──> Telephony
                   │  (Twilio)     (Deepgram) (OpenAI) (ElevenLabs)
                   └──────────────┘
```

## Providers

Each pipeline layer uses a **Protocol-based abstraction**, making providers swappable:

| Layer | Current Provider | Interface |
|---|---|---|
| Telephony | Twilio Media Streams | `TelephonyProvider` |
| STT | Deepgram Nova-3 | `STTProvider` |
| LLM | OpenAI (GPT-4o-mini) or Groq (Llama-3.1) | `LLMProvider` |
| TTS | ElevenLabs (Flash v2.5, streaming) | `TTSProvider` |

Swap a provider by changing a single line:
```python
stt = STTProvider.from_elevenlabs(api_key=...)   # current
# stt = STTProvider.from_deepgram(api_key=...)  # alternative
```

## Prerequisites

- **Python 3.12+**
- **ngrok** — to expose your local server to Twilio ([download](https://ngrok.com/download))
- **Twilio account** — with a phone number that supports Voice
- **Deepgram API key** — for speech-to-text ([sign up](https://console.deepgram.com))
- **OpenAI API key** — for the LLM and RAG Embeddings ([sign up](https://platform.openai.com))
- **Groq API key** *(Optional)* — if using the Groq LLM provider
- **ElevenLabs API key** — for text-to-speech ([sign up](https://elevenlabs.io))

## Setup

### 1. Clone and install

```bash
git clone <repo-url> VoiceKit
cd VoiceKit
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Edit the `.env` file in the project root:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

DEEPGRAM_API_KEY=your_deepgram_api_key
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
```

## Running

```bash
python run.py
```

This single command will:
1. Start an ngrok tunnel
2. Update your Twilio phone number's webhook automatically
3. Launch the FastAPI server

Then call your Twilio phone number and talk to the AI!

## Customizing the Agent

VoiceKit completely decouples the underlying framework from your specific business logic.

1. **Knowledge Base (RAG)**: Drop your `.pdf`, `.docx`, `.xlsx`, `.csv`, `.md`, `.html`, or `.txt` files directly into `business/knowledge_base/`. The built-in RAG engine uses LangChain, FAISS, and **FlashRank** to automatically parse, chunk, vectorize, and rerank them for maximum retrieval accuracy.
2. **Agent Persona**: Edit `business/prompt.txt` to give your agent a name, background, and specific behavioral instructions.
3. **Custom Tools**: Add Python functions to `business/tools/` and register them so the LLM can trigger real-world actions (e.g., booking appointments, fetching estimates).

## Project Structure

```
VoiceKit/
├── backend/
│   ├── main.py                      # FastAPI app, routes, pipeline wiring
│   ├── pipeline.py                  # Core streaming pipeline coordinator
│   ├── telephony/
│   │   ├── base.py                  # TelephonyProvider Protocol
│   │   └── twilio_provider.py       # Twilio Media Streams implementation
│   ├── stt/
│   │   ├── base.py                  # STTProvider Protocol + Transcript
│   │   └── deepgram_provider.py     # Deepgram real-time STT
│   ├── llm/
│   │   ├── base.py                  # LLMProvider Protocol + PipelineContext
│   │   └── openai_provider.py       # OpenAI streaming chat completions
│   ├── tts/
│   │   ├── base.py                  # TTSProvider Protocol
│   │   └── elevenlabs_provider.py   # ElevenLabs streaming TTS
│   ├── rag/
│   │   └── engine.py                # Multi-format LangChain/FAISS RAG Engine
│   └── utils/
│       └── audio.py                 # Audio format conversion (mu-law <-> PCM)
├── business/                        # Business logic (Decoupled from Framework)
│   ├── knowledge_base/              # Drop PDFs, Word Docs, Excels, HTML here
│   ├── tools/                       # Business-specific Python tools
│   └── prompt.txt                   # The agent's persona and instructions
├── testing/
│   └── softphone/                   # Browser-based softphone for testing
├── run.py                           # One-command launcher (ngrok + webhook + server)
├── requirements.txt
├── .env
└── README.md
```

## Testing with the Softphone

For testing without needing a real phone (useful when international carriers drop calls):

1. Start the main server: `python run.py`
2. In a new terminal: `python testing/softphone/run.py`
3. Open [http://localhost:8001/static/index.html](http://localhost:8001/static/index.html)
4. Click **Call** and talk to the AI.

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | `GET` | Health check -- returns `{"status": "ok"}` |
| `/voice` | `GET` / `POST` | Twilio webhook -- returns TwiML to start a `<Stream>` |
| `/media-stream` | `WebSocket` | Bidirectional audio stream (Twilio connects here) |

## Extensibility

The architecture is designed to support:
- **Dynamic RAG**: The `PipelineContext` object can carry retrieved documents to the LLM
- **Tool Calling**: Tool results can be injected into `PipelineContext` between STT and LLM
- **Provider Swapping**: Add a new provider by implementing the Protocol, then change one line
- **Barge-in**: Built-in support for interrupting the AI mid-speech

## RAG Benchmarks

The RAG engine is heavily tested and tuned for high accuracy retrieval on complex technical documents. 

Recent evaluations using the **Ragas** framework demonstrate:
- **Synthetic "Needle-in-a-haystack" Datasets:** 100% Context Precision, 96.3% Faithfulness.
- **Real-World Automotive Datasets:** 62.1% Context Precision, 82.8% Faithfulness.

## License

MIT
