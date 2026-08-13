"""picowave - host tooling for the pico_logic_gen waveform generator."""

from .format import (
    BASE_CLOCK_HZ,
    CHANNELS,
    MAX_WORD_DELAY,
    FormatError,
    PlwWaveform,
    validate_sample_clock,
)
from .waveform import Waveform

__version__ = "0.1.0"

__all__ = [
    "BASE_CLOCK_HZ",
    "CHANNELS",
    "MAX_WORD_DELAY",
    "FormatError",
    "PlwWaveform",
    "Waveform",
    "validate_sample_clock",
]
