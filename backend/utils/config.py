from typing import Optional
import yaml
from pydantic import BaseModel, Field

# --- Provider Configurations ---

class TwilioConfig(BaseModel):
    phone_number: str
    port: int = 8000

class DeepgramConfig(BaseModel):
    model: str = "nova-3"
    language: str = "en-US"

class OpenAIConfig(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 0.2

class GroqConfig(BaseModel):
    model: str = "llama-3.1-8b-instant"
    temperature: float = 0.2

class ElevenLabsConfig(BaseModel):
    voice_id: str

# --- Modality Blocks ---

class TelephonyBlock(BaseModel):
    provider: str
    twilio: Optional[TwilioConfig] = None

class STTBlock(BaseModel):
    provider: str
    deepgram: Optional[DeepgramConfig] = None

class LLMBlock(BaseModel):
    provider: str
    openai: Optional[OpenAIConfig] = None
    groq: Optional[GroqConfig] = None

class TTSBlock(BaseModel):
    provider: str
    elevenlabs: Optional[ElevenLabsConfig] = None

# --- Other Blocks ---

class AgentConfig(BaseModel):
    prompt: str
    tools_module: str

class RAGConfig(BaseModel):
    knowledge_base_dir: str
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 3

class VoiceKitConfig(BaseModel):
    telephony: TelephonyBlock
    stt: STTBlock
    llm: LLMBlock
    tts: TTSBlock
    agent: AgentConfig
    rag: RAGConfig

def load_config(config_path: str = "config.yaml") -> VoiceKitConfig:
    """Loads the VoiceKit config from a YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return VoiceKitConfig(**data)
