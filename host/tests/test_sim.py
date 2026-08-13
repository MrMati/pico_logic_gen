from picowave.format import PlwWaveform
from picowave.sim import edge_table, to_vcd
from picowave.waveform import Waveform

CANONICAL = [(10, 0xFF), (10, 0x00), (100, 0x55), (37, 0xAA), (5000, 0x00)]


def test_edge_table_contains_expected_positions():
    wf = PlwWaveform(initial_state=0x00, events=list(CANONICAL))
    table = edge_table(wf)
    for t in (10, 20, 120, 157, 5157):
        assert f"\n{t:>14}" in table
    assert "0xFF" in table and "0xAA" in table


def test_vcd_output():
    wf = PlwWaveform(initial_state=0x00, events=list(CANONICAL))
    vcd = to_vcd(wf)
    assert "$timescale 1 ps $end" in vcd
    # 25 MHz -> 40000 ps per sample; first edge at sample 10.
    assert "#400000" in vcd
    assert vcd.count("$var wire 1") == 8


def test_vcd_skips_no_change_events():
    wf = PlwWaveform(initial_state=0x00,
                     events=[(5, 0x01), (5, 0x01), (5, 0x00)])
    vcd = to_vcd(wf)
    # Only two value-change timestamps (plus #0 and the final marker).
    assert "#200000" in vcd and "#600000" in vcd
    assert "#400000" not in vcd


def test_builder_square_and_pulse():
    w = Waveform(initial=0x00)
    w.square(channel=0, period=8, cycles=2)
    w.pulse(channel=7, delay=10, width=3)
    wf = w.build()
    assert wf.events == [
        (4, 0x01), (4, 0x00), (4, 0x01), (4, 0x00),
        (10, 0x80), (3, 0x00),
    ]


def test_builder_bit_helpers():
    w = Waveform(initial=0x0F)
    w.set_bits(1, 0x30).clear_bits(2, 0x05).toggle_bits(3, 0xFF).hold(4)
    wf = w.build()
    assert wf.events == [(1, 0x3F), (2, 0x3A), (3, 0xC5), (4, 0xC5)]
