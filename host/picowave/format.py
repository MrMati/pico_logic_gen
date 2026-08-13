"""picowave.format - .plw binary waveform format.

Mirrors firmware/wave_format.h. See docs/FORMAT.md.

Layout (little-endian):

    offset  size  field
    0       4     magic            "PLW1"
    4       2     version          1
    6       2     flags            0
    8       4     sample_clock_hz  must divide 25 MHz, divider <= 65535
    12      1     channel_count    8
    13      1     initial_state
    14      2     reserved         0
    16      4     event_count      >= 1
    20      4     payload_crc32    CRC-32 (IEEE) of the event payload
    24      8*n   events           (u32 delay_samples, u32 state)
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

MAGIC = b"PLW1"
VERSION = 1
CHANNELS = 8
BASE_CLOCK_HZ = 25_000_000
MAX_CLKDIV = 65535
MAX_WORD_DELAY = 1 << 24  # max samples per PIO word; larger delays split

HEADER_STRUCT = struct.Struct("<4sHHIBBHII")
EVENT_STRUCT = struct.Struct("<II")

assert HEADER_STRUCT.size == 24
assert EVENT_STRUCT.size == 8


class FormatError(ValueError):
    """Raised for invalid .plw data."""


def validate_sample_clock(hz: int) -> int:
    """Return the integer PIO clock divider for a sample clock, or raise."""
    if hz <= 0 or BASE_CLOCK_HZ % hz != 0:
        raise FormatError(
            f"sample_clock_hz must be an integer divisor of {BASE_CLOCK_HZ}"
            f" (got {hz})"
        )
    div = BASE_CLOCK_HZ // hz
    if div > MAX_CLKDIV:
        raise FormatError(
            f"sample_clock_hz {hz} needs divider {div} > {MAX_CLKDIV}"
        )
    return div


@dataclass
class PlwWaveform:
    """A parsed/parseable .plw waveform."""

    initial_state: int = 0
    sample_clock_hz: int = BASE_CLOCK_HZ
    events: list[tuple[int, int]] = field(default_factory=list)  # (delay, state)

    def validate(self) -> None:
        validate_sample_clock(self.sample_clock_hz)
        if not 0 <= self.initial_state <= 0xFF:
            raise FormatError(f"initial_state out of range: {self.initial_state}")
        if not self.events:
            raise FormatError("waveform must contain at least one event")
        if len(self.events) > 0xFFFFFFFF:
            raise FormatError("too many events")
        for i, (delay, state) in enumerate(self.events):
            if not 1 <= delay <= 0xFFFFFFFF:
                raise FormatError(f"event {i}: delay must be in 1..2**32-1, got {delay}")
            if not 0 <= state <= 0xFF:
                raise FormatError(f"event {i}: state must be 0..255, got {state}")

    # -- derived quantities ------------------------------------------------

    @property
    def total_samples(self) -> int:
        """Total duration in samples (time of the last edge)."""
        return sum(d for d, _ in self.events)

    @property
    def duration_seconds(self) -> float:
        return self.total_samples / self.sample_clock_hz

    def edge_times(self) -> list[tuple[int, int]]:
        """[(t_samples, new_state)]: edge k occurs at t = sum(delays[:k+1])."""
        out = []
        t = 0
        for delay, state in self.events:
            t += delay
            out.append((t, state))
        return out

    def word_count(self) -> int:
        """Number of 32-bit PIO words the firmware will expand this to."""
        n = 0
        for delay, _ in self.events:
            n += 1 + (delay - 1) // MAX_WORD_DELAY
        return n

    # -- serialisation -----------------------------------------------------

    def payload_bytes(self) -> bytes:
        return b"".join(EVENT_STRUCT.pack(d, s) for d, s in self.events)

    def header_bytes(self) -> bytes:
        payload = self.payload_bytes()
        return HEADER_STRUCT.pack(
            MAGIC,
            VERSION,
            0,
            self.sample_clock_hz,
            CHANNELS,
            self.initial_state,
            0,
            len(self.events),
            zlib.crc32(payload) & 0xFFFFFFFF,
        )

    def to_bytes(self) -> bytes:
        self.validate()
        return self.header_bytes() + self.payload_bytes()

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.to_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> "PlwWaveform":
        if len(data) < HEADER_STRUCT.size:
            raise FormatError("file too short for header")
        (
            magic,
            version,
            flags,
            sample_clock_hz,
            channel_count,
            initial_state,
            reserved,
            event_count,
            payload_crc32,
        ) = HEADER_STRUCT.unpack_from(data, 0)
        if magic != MAGIC:
            raise FormatError(f"bad magic {magic!r}")
        if version != VERSION:
            raise FormatError(f"unsupported version {version}")
        if flags != 0 or reserved != 0:
            raise FormatError("flags/reserved must be 0")
        if channel_count != CHANNELS:
            raise FormatError(f"unsupported channel_count {channel_count}")
        payload = data[HEADER_STRUCT.size:]
        if len(payload) != event_count * EVENT_STRUCT.size:
            raise FormatError(
                f"payload length {len(payload)} does not match "
                f"event_count {event_count}"
            )
        if (zlib.crc32(payload) & 0xFFFFFFFF) != payload_crc32:
            raise FormatError("payload CRC mismatch")
        events = [
            EVENT_STRUCT.unpack_from(payload, i * EVENT_STRUCT.size)
            for i in range(event_count)
        ]
        wf = cls(
            initial_state=initial_state,
            sample_clock_hz=sample_clock_hz,
            events=[(d, s) for d, s in events],
        )
        wf.validate()
        return wf

    @classmethod
    def load(cls, path: str) -> "PlwWaveform":
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())
