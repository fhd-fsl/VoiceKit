"""
Audio format utilities for telephony media streams.

Twilio streams audio as 8 kHz, single-channel, 8-bit mu-law (G.711).
These helpers convert between mu-law and 16-bit linear PCM and provide
chunking utilities for smooth outbound streaming.
"""

import audioop
import base64

# ── Twilio media stream constants ────────────────────────────────────
MULAW_SAMPLE_RATE = 8000  # 8 kHz
MULAW_SAMPLE_WIDTH = 1  # 1 byte per sample (8-bit mu-law)
MULAW_CHANNELS = 1  # mono
PCM_SAMPLE_WIDTH = 2  # 2 bytes per sample (16-bit linear PCM)


def decode_mulaw(mulaw_bytes: bytes) -> bytes:
    """Convert 8-bit mu-law audio to 16-bit linear PCM.

    Args:
        mulaw_bytes: Raw mu-law encoded audio bytes.

    Returns:
        16-bit signed little-endian PCM bytes (sample width = 2).
    """
    return audioop.ulaw2lin(mulaw_bytes, PCM_SAMPLE_WIDTH)


def encode_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit linear PCM audio to 8-bit mu-law.

    Args:
        pcm_bytes: 16-bit signed little-endian PCM bytes.

    Returns:
        mu-law encoded audio bytes.
    """
    return audioop.lin2ulaw(pcm_bytes, PCM_SAMPLE_WIDTH)


def decode_payload(payload_b64: str) -> bytes:
    """Decode a base64-encoded mu-law payload from Twilio into raw mu-law bytes."""
    return base64.b64decode(payload_b64)


def encode_payload(mulaw_bytes: bytes) -> str:
    """Encode raw mu-law bytes into a base64 string for sending to Twilio."""
    return base64.b64encode(mulaw_bytes).decode("ascii")


def chunk_audio(data: bytes, chunk_ms: int = 20) -> list[bytes]:
    """Split mu-law audio bytes into fixed-duration chunks.

    Default 20 ms chunks -> 160 bytes each at 8 kHz / 1 byte per sample.
    This matches Twilio's own ~20 ms media event cadence.

    Args:
        data: Raw mu-law audio bytes to chunk.
        chunk_ms: Duration of each chunk in milliseconds.

    Returns:
        A list of byte chunks. The last chunk may be shorter than the
        requested duration if the input is not evenly divisible.
    """
    bytes_per_chunk = int(MULAW_SAMPLE_RATE * MULAW_SAMPLE_WIDTH * (chunk_ms / 1000))
    return [data[i : i + bytes_per_chunk] for i in range(0, len(data), bytes_per_chunk)]
