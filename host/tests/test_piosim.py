"""Cycle-accounting proof: step the waveplay PIO program instruction by
instruction and verify each edge lands on the exact requested cycle.

Covers the validation matrix from the design brief:
  1. square wave at a known period
  2. short and long delays
  3. simultaneous multi-bit transitions
  4. delays spanning the counter range (incl. 24-bit split)
"""

import random

from picowave.format import MAX_WORD_DELAY
from picowave.piosim import (
    PIO_CYCLES_PER_SAMPLE,
    encode_words,
    expected_change_cycles,
    simulate,
)

CANONICAL = [(10, 0xFF), (10, 0x00), (100, 0x55), (37, 0xAA), (5000, 0x00)]


def run(initial, events):
    words = encode_words(initial, events)
    return words, simulate(words)


def assert_exact(initial, events):
    """Every OUT PINS lands at PIO cycle 5*cumsum(N) - 2 exactly."""
    words = encode_words(initial, events)
    changes = simulate(words)
    # Splitting may add no-change filler words; reconstruct expected
    # per-word delays from the words themselves.
    t = 0
    assert len(changes) == len(words)
    for word, (cycle, state) in zip(words, changes):
        n = (word & 0xFFFFFF) + 1
        t += n
        assert cycle == PIO_CYCLES_PER_SAMPLE * t - 2, (
            f"edge expected at cycle {PIO_CYCLES_PER_SAMPLE * t - 2}, got {cycle}"
        )
        assert state == (word >> 24) & 0xFF


def test_canonical_vector():
    words, changes = run(0x00, CANONICAL)
    assert len(words) == 5  # no splitting needed
    # Edge k visible exactly at sample sum(N_1..N_k): cycle 5*t - 2.
    assert changes == [
        (5 * 10 - 2, 0xFF),
        (5 * 20 - 2, 0x00),
        (5 * 120 - 2, 0x55),
        (5 * 157 - 2, 0xAA),
        (5 * 5157 - 2, 0x00),
    ]


def test_min_delay_back_to_back():
    """N=1 events produce edges exactly one sample (5 cycles) apart."""
    events = [(1, i & 0xFF) for i in range(1, 50)]
    _, changes = run(0x00, events)
    cycles = [c for c, _ in changes]
    assert cycles[0] == 5 * 1 - 2
    assert all(b - a == 5 for a, b in zip(cycles, cycles[1:]))


def test_square_wave_period():
    period = 8  # samples
    events = []
    for _ in range(20):
        events.append((period // 2, 0x01))
        events.append((period // 2, 0x00))
    _, changes = run(0x00, events)
    cycles = [c for c, _ in changes]
    assert all(b - a == 5 * period // 2 for a, b in zip(cycles, cycles[1:]))


def test_simultaneous_multibit_transitions():
    events = [(3, 0xFF), (3, 0x00), (3, 0xA5), (3, 0x5A)]
    _, changes = run(0x00, events)
    # All 8 bits change in a single OUT: one change record per event.
    assert [s for _, s in changes] == [0xFF, 0x00, 0xA5, 0x5A]
    assert_exact(0x00, events)


def test_delay_counter_range():
    """Delays spanning the 24-bit counter range, incl. exact boundary."""
    events = [
        (1, 0x01),
        (2, 0x02),
        (0xFFFFFF, 0x03),          # max N-1 field value + 1... N = 2^24 - 1
        (MAX_WORD_DELAY, 0x04),    # N = 2^24, single word
        (MAX_WORD_DELAY + 1, 0x05),  # split into 2 words
    ]
    words = encode_words(0x00, events)
    assert len(words) == 6
    assert_exact(0x00, events)


def test_split_preserves_total_time_and_state():
    events = [(2 * MAX_WORD_DELAY + 123, 0x77)]
    words, changes = run(0x11, events)
    assert len(words) == 3
    # Filler words re-drive the previous state (0x11): no visible glitch.
    assert [s for _, s in changes] == [0x11, 0x11, 0x77]
    # Final edge at the exact requested total time.
    total = 2 * MAX_WORD_DELAY + 123
    assert changes[-1][0] == 5 * total - 2


def test_randomized_vectors():
    rng = random.Random(1234)
    for _ in range(20):
        events = []
        for _ in range(rng.randint(1, 200)):
            delay = rng.choice([
                rng.randint(1, 5),
                rng.randint(1, 1000),
                rng.randint(1, MAX_WORD_DELAY + 5),
            ])
            events.append((delay, rng.randint(0, 255)))
        assert_exact(rng.randint(0, 255), events)


def test_replay_identical():
    """Simulated replay of the same word buffer is event-for-event identical."""
    words = encode_words(0x00, CANONICAL)
    assert simulate(words) == simulate(words)
