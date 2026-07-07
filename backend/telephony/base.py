"""
Telephony provider protocol.

Defines the interface that all telephony providers (Twilio, Telnyx, etc.)
must implement to integrate with the VoiceKit pipeline.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class TelephonyProvider(Protocol):
    """Abstract interface for a telephony media stream connection.

    A telephony provider manages the real-time audio connection between
    a phone caller and the VoiceKit server. It receives inbound audio
    (caller's voice) and sends outbound audio (AI response) over
    the connection.

    Audio format: All audio is 8 kHz mono mu-law (G.711), which is the
    standard telephony codec. No conversion is needed between the
    telephony layer and providers that support mu-law natively.
    """

    @property
    def is_running(self) -> bool:
        """Whether the media stream is currently active."""
        ...

    @property
    def stream_id(self) -> str:
        """Provider-specific stream identifier (e.g., Twilio's streamSid)."""
        ...

    @property
    def call_id(self) -> str:
        """Provider-specific call identifier (e.g., Twilio's callSid)."""
        ...

    async def connect(self, websocket) -> None:
        """Accept and initialize the media stream connection.

        Args:
            websocket: The WebSocket connection from the telephony provider.
        """
        ...

    async def run(self) -> None:
        """Main receive loop — processes incoming messages until the stream ends.

        This method blocks until the call disconnects or the stream is stopped.
        While running, inbound audio is made available via ``inbound_audio()``.
        """
        ...

    def inbound_audio(self) -> asyncio.Queue[bytes]:
        """Queue of raw mu-law audio chunks received from the caller.

        Each chunk is a bytes object containing raw 8 kHz mono mu-law audio.
        Chunks arrive at approximately 20 ms intervals (~160 bytes each).
        """
        ...

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        """Send mu-law audio back to the caller.

        Args:
            mulaw_bytes: Raw 8 kHz mono mu-law audio bytes.
        """
        ...

    async def send_mark(self, label: str | None = None) -> str:
        """Send a playback position mark.

        Marks are acknowledged by the telephony provider when the audio
        preceding the mark has been played to the caller. This is useful
        for tracking playback progress and implementing barge-in.

        Args:
            label: Optional mark name. Auto-generated if not provided.

        Returns:
            The mark name that was sent.
        """
        ...

    async def clear_audio(self) -> None:
        """Flush the outbound audio buffer.

        Instructs the telephony provider to discard any queued outbound
        audio that hasn't been played yet. Essential for barge-in: when
        the caller starts speaking, clear queued TTS audio so the agent
        stops talking immediately.
        """
        ...

    async def close(self) -> None:
        """Gracefully close the media stream connection."""
        ...

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_twilio(cls) -> TelephonyProvider:
        """Create a Twilio Media Streams telephony provider."""
        from backend.telephony.twilio_provider import TwilioTelephony
        return TwilioTelephony()
