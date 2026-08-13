"""picowave.sim - waveform simulation, edge tables and VCD export."""

from __future__ import annotations

from .format import CHANNELS, PlwWaveform


def edge_table(wf: PlwWaveform) -> str:
    """Human-readable edge table in samples and nanoseconds."""
    ns_per_sample = 1e9 / wf.sample_clock_hz
    lines = [
        f"sample clock : {wf.sample_clock_hz} Hz"
        f" ({ns_per_sample:g} ns/sample)",
        f"initial state: 0x{wf.initial_state:02X}"
        f" ({wf.initial_state:08b})",
        "",
        f"{'t (samples)':>14}  {'t (ns)':>16}  state  bits",
    ]
    for t, state in wf.edge_times():
        lines.append(
            f"{t:>14}  {t * ns_per_sample:>16.1f}  0x{state:02X}   {state:08b}"
        )
    return "\n".join(lines)


def to_vcd(wf: PlwWaveform) -> str:
    """Export as a Value Change Dump for GTKWave / PulseView.

    Timescale is 1 ps; one sample = 1e12 / sample_clock_hz ps, which is
    exact for every supported sample clock (all divide 25 MHz, and
    25 MHz divides 1e12).
    """
    ps_per_sample = 10**12 // wf.sample_clock_hz
    ids = [chr(ord("!") + i) for i in range(CHANNELS)]
    bus_id = chr(ord("!") + CHANNELS)

    out = [
        "$timescale 1 ps $end",
        "$scope module pico_logic_gen $end",
    ]
    for i in range(CHANNELS):
        out.append(f"$var wire 1 {ids[i]} ch{i} $end")
    out.append(f"$var wire {CHANNELS} {bus_id} bus[{CHANNELS - 1}:0] $end")
    out += ["$upscope $end", "$enddefinitions $end"]

    def dump(state: int) -> list[str]:
        lines = [f"{(state >> i) & 1}{ids[i]}" for i in range(CHANNELS)]
        lines.append(f"b{state:0{CHANNELS}b} {bus_id}")
        return lines

    out.append("#0")
    out += dump(wf.initial_state)
    prev = wf.initial_state
    last_t = 0
    for t, state in wf.edge_times():
        last_t = t
        if state == prev:
            continue
        out.append(f"#{t * ps_per_sample}")
        out += dump(state)
        prev = state
    # Final timestamp so viewers show the full duration.
    out.append(f"#{(last_t + 1) * ps_per_sample}")
    return "\n".join(out) + "\n"
