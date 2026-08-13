import pytest

from picowave.format import FormatError
from picowave.textfmt import parse_text, to_text

CANONICAL_TEXT = """
# canonical test vector
initial 0x00
10   -> 0xFF
10   -> 0x00
100  -> 0x55
37   -> 0xAA
5000 -> 0x00
"""


def test_parse_canonical():
    wf = parse_text(CANONICAL_TEXT)
    assert wf.initial_state == 0x00
    assert wf.sample_clock_hz == 25_000_000
    assert wf.events == [(10, 0xFF), (10, 0x00), (100, 0x55),
                         (37, 0xAA), (5000, 0x00)]


def test_parse_clock_and_decimal():
    wf = parse_text("clock 1000000\ninitial 3\n5 -> 255\n")
    assert wf.sample_clock_hz == 1_000_000
    assert wf.initial_state == 3
    assert wf.events == [(5, 255)]


def test_roundtrip_text():
    wf = parse_text(CANONICAL_TEXT)
    assert parse_text(to_text(wf)).events == wf.events


def test_garbage_rejected():
    with pytest.raises(FormatError, match="line 1"):
        parse_text("hello world\n")


def test_zero_delay_rejected():
    with pytest.raises(FormatError):
        parse_text("0 -> 0x01\n")


def test_clock_after_events_rejected():
    with pytest.raises(FormatError):
        parse_text("1 -> 0x01\nclock 1000000\n")


def test_bad_clock_rejected():
    with pytest.raises(FormatError):
        parse_text("clock 24000000\n1 -> 0x01\n")
