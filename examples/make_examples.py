#!/usr/bin/env python3
"""Generate example .plw waveforms programmatically with picowave.

Run from the repo root after installing the host package:

    pip install ./host
    python examples/make_examples.py
"""

from picowave import Waveform


def burst_and_bus() -> Waveform:
    """Counter burst on the low nibble, then simultaneous bus flips."""
    w = Waveform(initial=0x00)
    for value in range(16):
        w.event(25, value)  # 1 us per step
    w.event(2500, 0x00)     # 100 us idle gap (single event)
    for _ in range(8):
        w.event(2, 0xFF)    # 80 ns all-high
        w.event(2, 0x00)    # 80 ns all-low: full-bus simultaneous edges
    return w


def main() -> None:
    burst_and_bus().save("examples/burst_and_bus.plw")
    print("wrote examples/burst_and_bus.plw")

    w = Waveform(initial=0x00)
    w.square(channel=0, period=10, cycles=20)  # 2.5 MHz on GP0
    w.save("examples/square_2p5mhz.plw")
    print("wrote examples/square_2p5mhz.plw")


if __name__ == "__main__":
    main()
