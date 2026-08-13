"""picowave.textfmt - human-editable text waveform format.

Example:

    # comment
    clock 25000000        # optional, default 25 MHz
    initial 0x00
    10   -> 0xFF          # hold 10 samples, then drive 0xFF
    10   -> 0x00
    100  -> 0x55
    37   -> 0xAA
    5000 -> 0x00
"""

from __future__ import annotations

from .format import BASE_CLOCK_HZ, FormatError, PlwWaveform


def _int(token: str) -> int:
    return int(token, 0)


def parse_text(text: str) -> PlwWaveform:
    wf = PlwWaveform(initial_state=0, sample_clock_hz=BASE_CLOCK_HZ)
    seen_event = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            if line.lower().startswith("clock"):
                if seen_event:
                    raise FormatError("'clock' must come before events")
                wf.sample_clock_hz = _int(line.split()[1])
            elif line.lower().startswith("initial"):
                if seen_event:
                    raise FormatError("'initial' must come before events")
                wf.initial_state = _int(line.split()[1])
            elif "->" in line:
                left, right = line.split("->", 1)
                delay = _int(left.strip())
                state = _int(right.strip())
                wf.events.append((delay, state))
                seen_event = True
            else:
                raise FormatError(f"unrecognized line: {line!r}")
        except (IndexError, ValueError) as e:
            if isinstance(e, FormatError):
                raise FormatError(f"line {lineno}: {e}") from None
            raise FormatError(f"line {lineno}: cannot parse {line!r}") from None
    wf.validate()
    return wf


def parse_file(path: str) -> PlwWaveform:
    with open(path, "r", encoding="utf-8") as f:
        return parse_text(f.read())


def to_text(wf: PlwWaveform) -> str:
    lines = [
        f"clock {wf.sample_clock_hz}",
        f"initial 0x{wf.initial_state:02X}",
    ]
    lines += [f"{delay} -> 0x{state:02X}" for delay, state in wf.events]
    return "\n".join(lines) + "\n"
