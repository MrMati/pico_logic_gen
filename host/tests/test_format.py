import struct
import zlib

import pytest

from picowave.format import (
    BASE_CLOCK_HZ,
    MAX_WORD_DELAY,
    FormatError,
    PlwWaveform,
    validate_sample_clock,
)

CANONICAL = [(10, 0xFF), (10, 0x00), (100, 0x55), (37, 0xAA), (5000, 0x00)]


def make_wf(**kw):
    return PlwWaveform(initial_state=0x00, events=list(CANONICAL), **kw)


def test_roundtrip():
    wf = make_wf()
    data = wf.to_bytes()
    wf2 = PlwWaveform.from_bytes(data)
    assert wf2.initial_state == wf.initial_state
    assert wf2.sample_clock_hz == BASE_CLOCK_HZ
    assert wf2.events == CANONICAL


def test_header_layout():
    data = make_wf().to_bytes()
    assert data[:4] == b"PLW1"
    assert struct.unpack_from("<H", data, 4)[0] == 1  # version
    assert struct.unpack_from("<I", data, 8)[0] == BASE_CLOCK_HZ
    assert data[12] == 8  # channels
    assert data[13] == 0x00  # initial state
    assert struct.unpack_from("<I", data, 16)[0] == len(CANONICAL)
    payload = data[24:]
    assert struct.unpack_from("<I", data, 20)[0] == zlib.crc32(payload)
    assert len(payload) == 8 * len(CANONICAL)


def test_crc_detects_corruption():
    data = bytearray(make_wf().to_bytes())
    data[30] ^= 0x01
    with pytest.raises(FormatError, match="CRC"):
        PlwWaveform.from_bytes(bytes(data))


def test_bad_magic_rejected():
    data = bytearray(make_wf().to_bytes())
    data[0] = ord("X")
    with pytest.raises(FormatError, match="magic"):
        PlwWaveform.from_bytes(bytes(data))


def test_bad_version_rejected():
    data = bytearray(make_wf().to_bytes())
    struct.pack_into("<H", data, 4, 99)
    with pytest.raises(FormatError, match="version"):
        PlwWaveform.from_bytes(bytes(data))


def test_zero_delay_rejected():
    wf = PlwWaveform(events=[(0, 0xFF)])
    with pytest.raises(FormatError, match="delay"):
        wf.validate()


def test_state_out_of_range_rejected():
    wf = PlwWaveform(events=[(1, 0x100)])
    with pytest.raises(FormatError, match="state"):
        wf.validate()


def test_empty_rejected():
    with pytest.raises(FormatError, match="at least one"):
        PlwWaveform().validate()


@pytest.mark.parametrize("hz,div", [
    (25_000_000, 1),
    (12_500_000, 2),
    (5_000_000, 5),
    (1_000_000, 25),
    (400, 62500),
])
def test_valid_sample_clocks(hz, div):
    assert validate_sample_clock(hz) == div


@pytest.mark.parametrize("hz", [0, -1, 24_000_000, 30_000_000, 33, 381])
def test_invalid_sample_clocks(hz):
    with pytest.raises(FormatError):
        validate_sample_clock(hz)


def test_edge_times_and_duration():
    wf = make_wf()
    assert wf.edge_times() == [
        (10, 0xFF), (20, 0x00), (120, 0x55), (157, 0xAA), (5157, 0x00),
    ]
    assert wf.total_samples == 5157
    assert wf.duration_seconds == pytest.approx(5157 / 25e6)


def test_word_count_with_splitting():
    wf = PlwWaveform(events=[(MAX_WORD_DELAY, 1), (MAX_WORD_DELAY + 1, 2),
                             (3 * MAX_WORD_DELAY + 7, 3)])
    # 1 word, 2 words, 4 words
    assert wf.word_count() == 7
