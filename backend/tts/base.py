"""
Text-to-speech provider protocol.

Defines the interface that all TTS providers (ElevenLabs, Google, etc.)
must implement to integrate with the VoiceKit pipeline.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    """Abstract interface for a streaming text-to-speech provider.

    A TTS provider converts streaming text into streaming audio.
    It accepts text chunks (e.g., from an LLM) and yields audio
    chunks as they are synthesized.

    Audio format: Providers should output 8 kHz mono mu-law audio,
    which can be sent directly to the telephony layer without conversion.
    If a provider outputs a different format, conversion should happen
    internally.
    """

    async def connect(self) -> None:
        """Open the streaming connection to the TTS service."""
        ...

    async def synthesize(
        self, text_stream: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        """Convert a stream of text tokens into a stream of audio chunks.

        This method consumes text tokens from the input iterator and
        yields mu-law audio chunks as they are synthesized. The method
        handles buffering and flushing internally.

        Args:
            text_stream: An async iterator yielding text tokens
                         (e.g., from the LLM provider).

        Yields:
            Raw 8 kHz mono mu-law audio byte chunks.
        """
        ...

    async def flush(self) -> AsyncIterator[bytes]:
        """Flush any buffered text and yield remaining audio.

        Call this after the text stream ends to ensure all text has
        been synthesized and all audio has been yielded.

        Yields:
            Any remaining mu-law audio byte chunks.
        """
        ...

    async def close(self) -> None:
        """Gracefully close the TTS connection."""
        ...

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_elevenlabs(
        cls,
        *,
        api_key: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model: str = "eleven_flash_v2_5",
        **kwargs,
    ) -> TTSProvider:
        """Create an ElevenLabs streaming TTS provider.

        Args:
            api_key: ElevenLabs API key.
            voice_id: ElevenLabs voice ID (default: George).
            model: Model name (default: eleven_flash_v2_5 for low latency).
            **kwargs: Additional options.
        """
        from backend.tts.elevenlabs_provider import ElevenLabsTTS
        return ElevenLabsTTS(
            api_key=api_key,
            voice_id=voice_id,
            model=model,
            **kwargs,
        )
