"""
Twilio Media Streams telephony provider.

Manages a single bidirectional media stream connection over WebSocket:
  - Inbound: receives mu-law audio from the caller, decodes and queues it.
  - Outbound: sends mu-law audio back to the caller, with support for
    playback marks and buffer clearing (barge-in).
"""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class StreamMetadata:
    """Metadata extracted from the Twilio 'start' event."""

    stream_sid: str = ""
    call_sid: str = ""
    account_sid: str = ""
    encoding: str = "audio/x-mulaw"
    sample_rate: int = 8000
    channels: int = 1
    tracks: list[str] = field(default_factory=lambda: ["inbound"])


class TwilioTelephony:
    """Twilio Media Streams implementation of TelephonyProvider.

    Handles the Twilio-specific WebSocket protocol for bidirectional
    audio streaming. Audio is 8 kHz mono mu-law (G.711).

    Usage:
        provider = TwilioTelephony()
        await provider.connect(websocket)
        await provider.run()  # blocks until stream ends
    """

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._meta = StreamMetadata()
        self._inbound_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._mark_counter = 0
        self._running = False

    # ── Properties ───────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether the media stream is currently active."""
        return self._running

    @property
    def stream_id(self) -> str:
        """Twilio's streamSid for this media stream."""
        return self._meta.stream_sid

    @property
    def call_id(self) -> str:
        """Twilio's callSid for this call."""
        return self._meta.call_sid

    # ── Public API ───────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        """Accept the WebSocket connection from Twilio."""
        self._ws = websocket
        await self._ws.accept()
        logger.info("Twilio WebSocket connection accepted")

    async def run(self) -> None:
        """Main receive loop -- processes Twilio messages until stream ends."""
        if not self._ws:
            raise RuntimeError("Must call connect() before run()")

        self._running = True
        logger.info("Waiting for Twilio media stream events")
        try:
            while self._running:
                raw = await self._ws.receive_text()
                msg = json.loads(raw)
                event = msg.get("event")

                if event == "connected":
                    self._handle_connected(msg)
                elif event == "start":
                    self._handle_start(msg)
                elif event == "media":
                    self._handle_media(msg)
                elif event == "mark":
                    self._handle_mark(msg)
                elif event == "stop":
                    self._handle_stop(msg)
                    break
                else:
                    logger.debug("Unknown Twilio event: %s", event)

        except WebSocketDisconnect:
            logger.info(
                "Twilio WebSocket disconnected (streamSid=%s)",
                self._meta.stream_sid,
            )
        except Exception:
            logger.exception("Error in Twilio media stream handler")
        finally:
            self._running = False
            logger.info(
                "Twilio media stream ended (streamSid=%s, callSid=%s)",
                self._meta.stream_sid,
                self._meta.call_sid,
            )

    def inbound_audio(self) -> asyncio.Queue[bytes]:
        """Queue of raw mu-law audio chunks from the caller."""
        return self._inbound_queue

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        """Send mu-law audio back to the caller."""
        if not self._ws or not self._meta.stream_sid:
            logger.warning("Cannot send audio -- stream not ready")
            return

        payload = base64.b64encode(mulaw_bytes).decode("ascii")
        message = json.dumps(
            {
                "event": "media",
                "streamSid": self._meta.stream_sid,
                "media": {"payload": payload},
            }
        )
        await self._ws.send_text(message)

    async def send_mark(self, label: str | None = None) -> str:
        """Send a playback position mark to Twilio."""
        if not self._ws or not self._meta.stream_sid:
            return ""

        if label is None:
            self._mark_counter += 1
            label = f"mark_{self._mark_counter}"

        message = json.dumps(
            {
                "event": "mark",
                "streamSid": self._meta.stream_sid,
                "mark": {"name": label},
            }
        )
        await self._ws.send_text(message)
        logger.debug("Sent mark: %s", label)
        return label

    async def clear_audio(self) -> None:
        """Flush Twilio's outbound audio buffer (for barge-in)."""
        if not self._ws or not self._meta.stream_sid:
            return

        message = json.dumps(
            {
                "event": "clear",
                "streamSid": self._meta.stream_sid,
            }
        )
        await self._ws.send_text(message)
        logger.info("Cleared Twilio audio buffer (streamSid=%s)", self._meta.stream_sid)

    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    # ── Private event handlers ───────────────────────────────────────

    def _handle_connected(self, msg: dict) -> None:
        protocol = msg.get("protocol", "unknown")
        version = msg.get("version", "unknown")
        logger.info(
            "Twilio stream connected (protocol=%s, version=%s)", protocol, version
        )

    def _handle_start(self, msg: dict) -> None:
        start = msg.get("start", {})
        self._meta.stream_sid = msg.get("streamSid", "")
        self._meta.call_sid = start.get("callSid", "")
        self._meta.account_sid = start.get("accountSid", "")

        media_format = start.get("mediaFormat", {})
        self._meta.encoding = media_format.get("encoding", self._meta.encoding)
        self._meta.sample_rate = int(
            media_format.get("sampleRate", self._meta.sample_rate)
        )
        self._meta.channels = int(
            media_format.get("channels", self._meta.channels)
        )
        self._meta.tracks = start.get("tracks", self._meta.tracks)

        logger.info(
            "Stream started -- streamSid=%s  callSid=%s  encoding=%s  "
            "sampleRate=%d  channels=%d  tracks=%s",
            self._meta.stream_sid,
            self._meta.call_sid,
            self._meta.encoding,
            self._meta.sample_rate,
            self._meta.channels,
            self._meta.tracks,
        )

    def _handle_media(self, msg: dict) -> None:
        media = msg.get("media", {})
        payload_b64 = media.get("payload", "")
        if payload_b64:
            audio_bytes = base64.b64decode(payload_b64)
            self._inbound_queue.put_nowait(audio_bytes)

    def _handle_mark(self, msg: dict) -> None:
        mark_name = msg.get("mark", {}).get("name", "unknown")
        logger.debug("Received mark acknowledgement: %s", mark_name)

    def _handle_stop(self, msg: dict) -> None:
        logger.info(
            "Stream stop received (streamSid=%s, callSid=%s)",
            self._meta.stream_sid,
            self._meta.call_sid,
        )
