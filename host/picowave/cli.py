"""picowave.cli - command line interface.

    picowave build wave.txt -o wave.plw
    picowave info wave.plw
    picowave sim wave.plw --vcd out.vcd
    picowave upload wave.plw [-p PORT]
    picowave play | stop | status | clear | id [-p PORT]
    picowave ports
"""

from __future__ import annotations

import argparse
import sys

from .format import FormatError, PlwWaveform
from .sim import edge_table, to_vcd
from .textfmt import parse_file


def _load_any(path: str) -> PlwWaveform:
    """Load .plw binary or text waveform based on content."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head == b"PLW1":
        return PlwWaveform.load(path)
    return parse_file(path)


def _open_device(args):
    from .device import Device, find_ports

    port = args.port
    if not port:
        ports = find_ports()
        if not ports:
            sys.exit("no serial ports found; specify one with -p")
        port = ports[0]
        print(f"using port {port}", file=sys.stderr)
    return Device(port)


def cmd_build(args) -> None:
    wf = _load_any(args.input)
    wf.save(args.output)
    print(f"wrote {args.output}: {len(wf.events)} events, "
          f"{wf.word_count()} PIO words, "
          f"{wf.duration_seconds * 1e3:.6g} ms")


def cmd_info(args) -> None:
    wf = _load_any(args.input)
    print(f"file            : {args.input}")
    print(f"sample clock    : {wf.sample_clock_hz} Hz")
    print(f"initial state   : 0x{wf.initial_state:02X}")
    print(f"events          : {len(wf.events)}")
    print(f"PIO words       : {wf.word_count()}")
    print(f"total samples   : {wf.total_samples}")
    print(f"duration        : {wf.duration_seconds * 1e3:.6g} ms")


def cmd_sim(args) -> None:
    wf = _load_any(args.input)
    print(edge_table(wf))
    if args.vcd:
        with open(args.vcd, "w", encoding="utf-8") as f:
            f.write(to_vcd(wf))
        print(f"\nwrote VCD: {args.vcd}")


def cmd_upload(args) -> None:
    wf = _load_any(args.input)
    with _open_device(args) as dev:
        def progress(done, total):
            print(f"\rupload {done}/{total} bytes", end="", file=sys.stderr)

        dev.upload(wf, progress=progress)
        print("", file=sys.stderr)
        st = dev.status()
        print(f"uploaded: {st.event_count} events -> {st.word_count} PIO "
              f"words @ {st.sample_clock_hz} Hz, state {st.state_name}")
        if args.play:
            dev.play()
            print("playback started")


def cmd_id(args) -> None:
    with _open_device(args) as dev:
        ident = dev.identify()
        print(f"firmware version: {ident.fw_version}")
        print(f"channels        : {ident.channel_count}")
        print(f"max PIO words   : {ident.max_words}")
        print(f"base clock      : {ident.base_clock_hz} Hz")


def cmd_status(args) -> None:
    with _open_device(args) as dev:
        st = dev.status()
        print(f"state           : {st.state_name}")
        print(f"last error      : {st.last_error}")
        print(f"initial state   : 0x{st.initial_state:02X}")
        print(f"events          : {st.event_count}")
        print(f"PIO words       : {st.word_count}")
        print(f"sample clock    : {st.sample_clock_hz} Hz")
        print(f"plays completed : {st.plays_completed}")
        print(f"payload CRC32   : 0x{st.payload_crc32:08X}")


def cmd_play(args) -> None:
    with _open_device(args) as dev:
        dev.play()
        print("playback started")


def cmd_stop(args) -> None:
    with _open_device(args) as dev:
        dev.stop()
        print("playback stopped")


def cmd_clear(args) -> None:
    with _open_device(args) as dev:
        dev.clear()
        print("waveform cleared")


def cmd_ports(_args) -> None:
    from .device import find_ports

    for p in find_ports():
        print(p)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="picowave")
    sub = ap.add_subparsers(dest="command", required=True)

    def add_port(p):
        p.add_argument("-p", "--port", help="serial port (default: auto)")

    p = sub.add_parser("build", help="compile text waveform to .plw")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("info", help="show waveform information")
    p.add_argument("input")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("sim", help="print edge table, optionally write VCD")
    p.add_argument("input")
    p.add_argument("--vcd", help="write VCD file for GTKWave/PulseView")
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser("upload", help="upload waveform to device")
    p.add_argument("input")
    p.add_argument("--play", action="store_true", help="start playback after upload")
    add_port(p)
    p.set_defaults(func=cmd_upload)

    for name, fn, help_ in [
        ("id", cmd_id, "identify device"),
        ("status", cmd_status, "query device status"),
        ("play", cmd_play, "start playback"),
        ("stop", cmd_stop, "stop playback"),
        ("clear", cmd_clear, "clear loaded waveform"),
    ]:
        p = sub.add_parser(name, help=help_)
        add_port(p)
        p.set_defaults(func=fn)

    p = sub.add_parser("ports", help="list candidate serial ports")
    p.set_defaults(func=cmd_ports)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except FormatError as e:
        sys.exit(f"waveform error: {e}")


if __name__ == "__main__":
    main()
