"""
ElevenLabs streaming text-to-speech provider.

Uses ElevenLabs' WebSocket streaming API to convert text tokens
into mu-law audio chunks in real time. Output format is ulaw_8000
which matches Twilio's native format — no conversion needed.
"""

import asyncio
import base64
import json
import logging
from typing import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

# Sentence-ending punctuation that triggers generation
_SENTENCE_ENDERS = {".", "!", "?", ":", ";", ",", "-"}


class ElevenLabsTTS:
    """ElevenLabs implementation of TTSProvider.

    Connects to the ElevenLabs WebSocket streaming API and converts
    text tokens into 8 kHz mu-law audio chunks suitable for Twilio.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model: str = "eleven_flash_v2_5",
        **kwargs,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._kwargs = kwargs
        self._ws = None
        self._connected = False

    async def connect(self) -> None:
        """Connection is established per-synthesis for ElevenLabs."""
        pass

    async def synthesize(
        self, text_stream: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        """Convert a stream of text tokens into mu-law audio chunks."""
        # 1. Start fetching LLM tokens immediately to hide WS connection latency
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def fetch_tokens():
            try:
                async for token in text_stream:
                    await token_queue.put(token)
            except Exception:
                pass
            finally:
                await token_queue.put(None)

        fetch_task = asyncio.create_task(fetch_tokens())

        async def queue_iterator() -> AsyncIterator[str]:
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                yield token

        url = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/"
            f"{self._voice_id}/stream-input"
            f"?model_id={self._model}"
            f"&output_format=ulaw_8000"
        )

        try:
            ws = await websockets.connect(url)
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error("ElevenLabs TTS rejected connection (HTTP %s). Check API key and credits.", e.status_code)
            fetch_task.cancel()
            return
        except Exception as e:
            logger.exception("Failed to connect to ElevenLabs TTS: %s", e)
            fetch_task.cancel()
            return

        # Send initial configuration
        init_msg = json.dumps(
            {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
                "xi_api_key": self._api_key,
                "generation_config": {
                    "chunk_length_schedule": [50],
                },
            }
        )
        await ws.send(init_msg)

        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        # Start concurrent sender and receiver tasks
        sender_task = asyncio.create_task(
            self._send_text(ws, queue_iterator(), audio_queue)
        )

        try:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if not sender_task.done():
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
            try:
                await ws.close()
            except Exception:
                pass

    async def flush(self) -> AsyncIterator[bytes]:
        """No-op for one-shot connections."""
        yield b""

    async def close(self) -> None:
        """No-op for one-shot connections."""
        pass

    # ── Private helpers ──────────────────────────────────────────────

    async def _send_text(
        self,
        ws: websockets.WebSocketClientProtocol,
        text_stream: AsyncIterator[str],
        audio_queue: asyncio.Queue[bytes | None],
    ) -> None:
        """Send text tokens to ElevenLabs and receive audio responses."""
        receiver_task = asyncio.create_task(self._receive_audio(ws, audio_queue))

        try:
            async for token in text_stream:
                if token:
                    await self._send_chunk(ws, token)

            # Signal end of text input
            await ws.send(json.dumps({"text": ""}))
            logger.debug("TTS: sent end-of-text flush signal")

        except Exception:
            logger.exception("Error sending text to ElevenLabs")
        finally:
            # Wait for the receiver to finish processing
            await receiver_task

    async def _send_chunk(self, ws: websockets.WebSocketClientProtocol, text: str) -> None:
        """Send a text chunk to ElevenLabs for synthesis."""

        msg = json.dumps(
            {
                "text": text,
                "try_trigger_generation": True,
            }
        )
        await ws.send(msg)
        logger.debug("TTS: sent text chunk (%d chars)", len(text))

    async def _receive_audio(
        self, ws: websockets.WebSocketClientProtocol, audio_queue: asyncio.Queue[bytes | None]
    ) -> None:
        """Receive audio chunks from ElevenLabs and put them on the queue."""
        try:
            async for msg in ws:
                data = json.loads(msg)

                if "error" in data:
                    logger.error("ElevenLabs TTS Error: %s", data["error"])
                    break

                if audio_b64 := data.get("audio"):
                    audio_bytes = base64.b64decode(audio_b64)
                    if audio_bytes:
                        await audio_queue.put(audio_bytes)

                if data.get("isFinal"):
                    logger.debug("TTS: received final audio chunk")
                    break

        except websockets.exceptions.ConnectionClosed:
            logger.debug("ElevenLabs WebSocket closed during receive")
        except Exception:
            logger.exception("Error receiving audio from ElevenLabs")
        finally:
            await audio_queue.put(None)
