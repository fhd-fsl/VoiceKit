"""
Deepgram real-time speech-to-text provider.

Uses Deepgram's live transcription WebSocket API to convert
streaming mu-law audio into text transcripts in real time.
"""

import asyncio
import logging
from typing import AsyncIterator

from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents,
)

from backend.stt.base import Transcript

logger = logging.getLogger(__name__)


class DeepgramSTT:
    """Deepgram implementation of STTProvider.

    Streams raw 8 kHz mu-law audio to Deepgram and yields
    Transcript objects as they arrive.
    """

    def __init__(self, *, api_key: str, **kwargs) -> None:
        self._api_key = api_key
        self._kwargs = kwargs
        self._connection = None
        self._transcript_queue: asyncio.Queue[Transcript | None] = asyncio.Queue()
        self._connected = False
        self._loop = None

    async def connect(self) -> None:
        """Open a live transcription connection to Deepgram."""
        self._loop = asyncio.get_running_loop()
        client = DeepgramClient(self._api_key)
        self._connection = client.listen.asynclive.v("1")

        # Register event handlers
        self._connection.on(
            LiveTranscriptionEvents.Transcript, self._on_transcript
        )
        self._connection.on(
            LiveTranscriptionEvents.UtteranceEnd, self._on_utterance_end
        )
        self._connection.on(
            LiveTranscriptionEvents.Error, self._on_error
        )
        self._connection.on(
            LiveTranscriptionEvents.Close, self._on_close
        )

        options = LiveOptions(
            model=self._kwargs.get("model", "nova-3"),
            language=self._kwargs.get("language", "en-US"),
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            smart_format=True,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            endpointing=300,
        )

        started = await self._connection.start(options)
        if started:
            self._connected = True
            logger.info("Deepgram live transcription connection opened")
        else:
            logger.error("Failed to start Deepgram connection")
            raise ConnectionError("Could not connect to Deepgram")

    async def send_audio(self, audio: bytes) -> None:
        """Send raw mu-law audio bytes to Deepgram."""
        if self._connection and self._connected:
            try:
                await self._connection.send(audio)
            except Exception as e:
                logger.debug("Failed to send audio to Deepgram: %s", e)
                self._connected = False

    async def transcripts(self) -> AsyncIterator[Transcript]:
        """Yield Transcript objects as they arrive from Deepgram."""
        while True:
            transcript = await self._transcript_queue.get()
            if transcript is None:
                # Sentinel value signals end of stream
                break
            yield transcript

    async def close(self) -> None:
        """Close the Deepgram connection."""
        self._connected = False
        if self._connection:
            try:
                await self._connection.finish()
            except Exception:
                logger.debug("Deepgram connection already closed")
        # Signal the transcript generator to stop
        if self._loop:
            self._loop.call_soon_threadsafe(self._transcript_queue.put_nowait, None)
        logger.info("Deepgram connection closed")

    # ── Event handlers ───────────────────────────────────────────────

    async def _on_transcript(self, _self, result, **kwargs) -> None:
        """Handle incoming transcript events from Deepgram."""
        try:
            alt = result.channel.alternatives[0]
            text = alt.transcript.strip()
            if not text:
                return

            transcript = Transcript(
                text=text,
                is_final=result.is_final,
                confidence=alt.confidence,
                speech_final=result.speech_final,
            )
            if self._loop:
                self._loop.call_soon_threadsafe(self._transcript_queue.put_nowait, transcript)

            if result.is_final:
                logger.info("STT [final]: %s", text)
            else:
                logger.debug("STT [interim]: %s", text)

        except (IndexError, AttributeError) as e:
            logger.debug("Could not parse transcript event: %s", e)

    async def _on_utterance_end(self, _self, utterance_end, **kwargs) -> None:
        """Handle utterance end events (speaker stopped talking)."""
        logger.debug("Deepgram utterance end detected")
        if self._loop:
            self._loop.call_soon_threadsafe(
                self._transcript_queue.put_nowait,
                Transcript(text="", is_final=True, speech_final=True)
            )

    async def _on_error(self, _self, error, **kwargs) -> None:
        """Handle Deepgram errors."""
        logger.error("Deepgram error encountered: %s", error)
        if self._loop:
            # We don't necessarily kill the connection, but we log prominently
            pass

    async def _on_close(self, _self, close, **kwargs) -> None:
        """Handle Deepgram connection close."""
        self._connected = False
        logger.info("Deepgram connection closed by server")
        if self._loop:
            self._loop.call_soon_threadsafe(self._transcript_queue.put_nowait, None)
