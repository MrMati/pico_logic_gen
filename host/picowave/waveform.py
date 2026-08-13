"""picowave.waveform - programmatic waveform builder."""

from __future__ import annotations

from .format import BASE_CLOCK_HZ, FormatError, PlwWaveform


class Waveform:
    """Builder for event/transition waveforms.

    Semantics: the outputs drive `initial` at t = 0. Each event holds
    the current state for `delay` samples and then drives `state`.

        w = Waveform(initial=0x00)
        w.event(10, 0xFF)   # edge at t = 10 samples
        w.event(10, 0x00)   # edge at t = 20 samples
        w.save("wave.plw")
    """

    def __init__(self, initial: int = 0, sample_clock_hz: int = BASE_CLOCK_HZ):
        self._wf = PlwWaveform(
            initial_state=initial, sample_clock_hz=sample_clock_hz
        )
        self._cur = initial

    @property
    def current_state(self) -> int:
        return self._cur

    def event(self, delay: int, state: int) -> "Waveform":
        """Hold the current state for `delay` samples, then drive `state`."""
        if delay < 1:
            raise FormatError("delay must be >= 1 sample")
        self._wf.events.append((delay, state))
        self._cur = state
        return self

    def hold(self, delay: int) -> "Waveform":
        """Keep the current state for `delay` extra samples."""
        return self.event(delay, self._cur)

    def set_bits(self, delay: int, mask: int) -> "Waveform":
        return self.event(delay, self._cur | mask)

    def clear_bits(self, delay: int, mask: int) -> "Waveform":
        return self.event(delay, self._cur & ~mask & 0xFF)

    def toggle_bits(self, delay: int, mask: int) -> "Waveform":
        return self.event(delay, self._cur ^ mask)

    def square(self, channel: int, period: int, cycles: int) -> "Waveform":
        """Square wave on one channel: high for period/2, low for period/2.

        `period` must be even and >= 2 samples.
        """
        if period < 2 or period % 2 != 0:
            raise FormatError("square period must be even and >= 2")
        half = period // 2
        mask = 1 << channel
        for _ in range(cycles):
            self.set_bits(half, mask)
            self.clear_bits(half, mask)
        return self

    def pulse(self, channel: int, delay: int, width: int) -> "Waveform":
        """After `delay` samples, drive channel high for `width` samples."""
        mask = 1 << channel
        self.set_bits(delay, mask)
        self.clear_bits(width, mask)
        return self

    def build(self) -> PlwWaveform:
        self._wf.validate()
        return self._wf

    def save(self, path: str) -> None:
        self.build().save(path)
