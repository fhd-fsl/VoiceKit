"""
Speech-to-text provider protocol.

Defines the interface that all STT providers (Deepgram, Whisper, etc.)
must implement to integrate with the VoiceKit pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class Transcript:
    """A single transcript result from the STT provider.

    Attributes:
        text: The transcribed text.
        is_final: Whether this is a final result (True) or an interim/partial
                  result (False). Final results won't change; interim results
                  may be updated as more audio arrives.
        confidence: Confidence score between 0.0 and 1.0.
        speech_final: Whether this marks the end of an utterance (i.e., the
                      speaker has paused). This is distinct from ``is_final``:
                      a provider may send multiple ``is_final=True`` chunks
                      within a single utterance, but ``speech_final=True``
                      indicates the speaker has stopped talking.
    """

    text: str = ""
    is_final: bool = False
    confidence: float = 0.0
    speech_final: bool = False


@runtime_checkable
class STTProvider(Protocol):
    """Abstract interface for a real-time speech-to-text provider.

    An STT provider maintains a persistent streaming connection to a
    transcription service. Raw audio is fed in, and transcript objects
    are yielded as they become available.

    Audio format: Providers should accept 8 kHz mono mu-law audio, which
    is the native format from the telephony layer. If a provider requires
    a different format, the conversion should happen internally.
    """

    async def connect(self) -> None:
        """Open the streaming connection to the STT service."""
        ...

    async def send_audio(self, audio: bytes) -> None:
        """Stream a chunk of raw audio to the STT service.

        Args:
            audio: Raw 8 kHz mono mu-law audio bytes.
        """
        ...

    async def transcripts(self) -> AsyncIterator[Transcript]:
        """Yield transcripts as they arrive from the STT service.

        This is an async generator that yields ``Transcript`` objects
        for both interim and final results. The generator completes
        when the connection is closed.

        Yields:
            Transcript objects with the transcribed text and metadata.
        """
        ...

    async def close(self) -> None:
        """Gracefully close the STT connection."""
        ...

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_deepgram(cls, *, api_key: str, **kwargs) -> STTProvider:
        """Create a Deepgram real-time STT provider.

        Args:
            api_key: Deepgram API key.
            **kwargs: Additional options passed to Deepgram LiveOptions.
        """
        from backend.stt.deepgram_provider import DeepgramSTT
        return DeepgramSTT(api_key=api_key, **kwargs)


