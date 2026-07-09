# VoiceKit

A modular, real-time voice AI framework that connects phone calls to a streaming AI pipeline via Twilio Media Streams. Calls flow through a fully swappable provider pipeline: **Telephony → STT → LLM → TTS → Telephony**, with built-in RAG, tool calling, and barge-in support.

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
                   │  (Twilio)    (Deepgram) (OpenAI/Groq) (ElevenLabs)
                   └──────────────┘
```

## Providers

Each pipeline layer uses a **Protocol-based abstraction**, making providers fully swappable via `config.yaml`:

| Layer | Providers | Interface |
|---|---|---|
| Telephony | Twilio Media Streams | `TelephonyProvider` |
| STT | Deepgram (Nova-3, Nova-2, Whisper) | `STTProvider` |
| LLM | OpenAI (GPT-4o-mini, GPT-4o) / Groq (Llama-3.1, Llama-3.3, Mixtral, Gemma) | `LLMProvider` |
| TTS | ElevenLabs (Flash v2.5, streaming WebSocket) | `TTSProvider` |

Switch between providers by changing a single field in `config.yaml`:
```yaml
llm:
  provider: "groq"       # swap to "openai" anytime
```

## Prerequisites

- **Python 3.12+**
- **ngrok** — to expose your local server to Twilio ([download](https://ngrok.com/download))
- **Twilio account** — with a phone number that supports Voice
- **Deepgram API key** — for speech-to-text ([sign up](https://console.deepgram.com))
- **OpenAI API key** — for the LLM and RAG embeddings ([sign up](https://platform.openai.com))
- **Groq API key** *(optional)* — alternative LLM provider with lower latency ([sign up](https://console.groq.com))
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

### 2. Configure

VoiceKit uses two configuration files:

1. **`.env`** — API keys and secrets. Copy `.env.example` to `.env` and fill in your credentials:
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: auto-authenticate ngrok
NGROK_AUTHTOKEN=your_ngrok_token_here

DEEPGRAM_API_KEY=your_deepgram_api_key
OPENAI_API_KEY=your_openai_api_key
GROQ_API_KEY=your_groq_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

2. **`config.yaml`** — Pipeline behavior. This single file controls the agent's system prompt, which providers to use, model selection, RAG parameters, and more. The file is validated against `config.schema.json` for IDE auto-completion and error checking.

## Running

```bash
python run.py
```

This single command will:
1. Start an ngrok tunnel
2. Update your Twilio phone number's webhook automatically
3. Launch the FastAPI server

Then call your Twilio phone number and talk to the AI.

> **Note:** The Twilio phone number is configured in `config.yaml` under `telephony.twilio.phone_number`, not in `.env`.

## Customizing the Agent

VoiceKit completely decouples the framework from your business logic. Everything under `business/` is yours to customize:

1. **Knowledge Base (RAG):** Drop `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.md`, `.html`, or `.txt` files into `business/knowledge_base/`. The RAG engine automatically parses, chunks, embeds (OpenAI), indexes (FAISS), and reranks (FlashRank) them.

2. **Agent Persona:** Define your agent's personality and instructions directly in `config.yaml` under the `agent.prompt` field:
    ```yaml
    agent:
      prompt: |
        Your name is Alex.
        You are a helpful assistant for Acme Corp...
    ```

3. **Custom Tools:** Add async Python functions to `business/tools/` and register them so the LLM can trigger actions during a call (e.g., booking appointments, looking up orders).

    **Requirements for custom tools:**
    - All tool functions **must** be `async def`.
    - Tools must be registered in the module specified by `agent.tools_module` in `config.yaml` (default: `business.tools.registry`).
    - The registry module must expose two variables:
      - `BUSINESS_TOOLS_SCHEMA` — a list of tool definitions in [OpenAI's function calling format](https://platform.openai.com/docs/guides/function-calling).
      - `BUSINESS_TOOL_FUNCTIONS` — a `dict[str, Callable]` mapping each tool name to its async function.

## Project Structure

```
VoiceKit/
├── backend/                             # Core framework (do not modify for business logic)
│   ├── main.py                          # FastAPI app, routes, Twilio webhook
│   ├── prompts.py                       # Framework-level system prompt rules
│   ├── pipeline/                        # Voice pipeline coordinator
│   ├── telephony/                       # Telephony providers (Twilio)
│   ├── stt/                             # STT providers (Deepgram)
│   ├── llm/                             # LLM providers (OpenAI, Groq)
│   ├── tts/                             # TTS providers (ElevenLabs)
│   ├── rag/                             # RAG engine (LangChain + FAISS + FlashRank)
│   ├── tools/                           # Framework tool schemas (e.g. search_knowledgebase)
│   └── utils/                           # Audio conversion, config loader
├── business/                            # Your business logic (fully customizable)
│   ├── knowledge_base/                  # Drop documents here for RAG
│   └── tools/                           # Your custom tool functions + registry
├── run.py                               # One-command launcher (ngrok + webhook + server)
├── config.yaml                          # Central pipeline configuration
├── config.schema.json                   # JSON Schema for config validation & IDE support
├── requirements.txt
├── .env.example                         # Template for API keys
└── README.md
```

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | `GET` | Health check — returns `{"status": "ok"}` |
| `/voice` | `GET` / `POST` | Twilio webhook — returns TwiML to open a `<Stream>` |
| `/media-stream` | `WebSocket` | Bidirectional audio stream (Twilio connects here) |

## Key Features

- **Provider Swapping:** Switch STT, LLM, or TTS providers by changing one line in `config.yaml`.
- **RAG (Retrieval-Augmented Generation):** Automatic document ingestion, chunking, embedding, and reranking with caching.
- **Native Tool Calling:** LLM can execute async Python functions mid-conversation using the OpenAI tool calling API.
- **Barge-in:** Users can interrupt the AI mid-speech; the pipeline cancels the current response and listens immediately.
- **Filler Phrases:** While the LLM executes a tool (e.g., RAG search), the agent speaks a natural filler phrase so the caller doesn't hear silence.

## RAG Benchmarks

The RAG engine has been evaluated using the **Ragas** framework:

| Dataset | Context Precision | Faithfulness |
|---|---|---|
| Synthetic (needle-in-a-haystack) | 100% | 96.3% |
| Real-world (200+ documents) | 62.1% | 82.8% |

## License

MIT
