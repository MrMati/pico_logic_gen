"""picowave.device - USB CDC protocol client.

Frame format (both directions, little-endian):

    sync(1) | cmd_or_status(1) | len(2) | payload | crc32(4)

with sync 0xA5 host->device and 0x5A device->host; the CRC covers
cmd/status + len + payload. See docs/PROTOCOL.md.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from .format import PlwWaveform

SYNC_REQ = 0xA5
SYNC_RESP = 0x5A

CMD_ID = 0x01
CMD_UPLOAD_BEGIN = 0x10
CMD_UPLOAD_DATA = 0x11
CMD_UPLOAD_END = 0x12
CMD_STATUS = 0x20
CMD_PLAY = 0x21
CMD_STOP = 0x22
CMD_CLEAR = 0x23

STATUS_NAMES = {
    0: "OK",
    1: "BAD_CMD",
    2: "BAD_CRC",
    3: "BAD_STATE",
    4: "BAD_FORMAT",
    5: "TOO_BIG",
    6: "BAD_RATE",
    7: "UPLOAD_SEQ",
    8: "BAD_LENGTH",
    9: "PAYLOAD_CRC",
    10: "BAD_DELAY",
}

STATE_NAMES = {
    0: "IDLE",
    1: "RECEIVING",
    2: "LOADED",
    3: "PLAYING",
    4: "COMPLETE",
    5: "ERROR",
}

UPLOAD_CHUNK = 1024  # bytes of event payload per UPLOAD_DATA frame

# Raspberry Pi (pico-sdk stdio USB CDC)
PICO_VID = 0x2E8A


class ProtocolError(RuntimeError):
    pass


class DeviceError(ProtocolError):
    def __init__(self, status: int):
        self.status = status
        name = STATUS_NAMES.get(status, f"status {status}")
        super().__init__(f"device returned error: {name}")


@dataclass
class DeviceStatus:
    state: int
    last_error: int
    channel_count: int
    initial_state: int
    event_count: int
    word_count: int
    sample_clock_hz: int
    plays_completed: int
    payload_crc32: int

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self.state, f"state {self.state}")


@dataclass
class DeviceId:
    fw_version: int
    channel_count: int
    max_words: int
    base_clock_hz: int


def find_ports() -> list[str]:
    """Candidate serial ports (Raspberry Pi VID first)."""
    pico = []
    other = []
    for p in list_ports.comports():
        if p.vid == PICO_VID:
            pico.append(p.device)
        else:
            other.append(p.device)
    return pico + other


class Device:
    def __init__(self, port: str, timeout: float = 3.0):
        self.ser = serial.Serial(port, baudrate=115200, timeout=timeout)

    def close(self) -> None:
        self.ser.close()

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- framing -----------------------------------------------------------

    def _send(self, cmd: int, payload: bytes = b"") -> None:
        body = struct.pack("<BH", cmd, len(payload)) + payload
        frame = bytes([SYNC_REQ]) + body + struct.pack("<I", zlib.crc32(body))
        self.ser.write(frame)

    def _read_exact(self, n: int) -> bytes:
        data = self.ser.read(n)
        if len(data) != n:
            raise ProtocolError("timeout reading from device")
        return data

    def _recv(self) -> tuple[int, bytes]:
        # Hunt for the sync byte to resynchronise after noise.
        for _ in range(4096):
            b = self.ser.read(1)
            if not b:
                raise ProtocolError("timeout waiting for response")
            if b[0] == SYNC_RESP:
                break
        else:
            raise ProtocolError("no response sync byte found")
        head = self._read_exact(3)
        status, length = struct.unpack("<BH", head)
        payload = self._read_exact(length) if length else b""
        (crc,) = struct.unpack("<I", self._read_exact(4))
        if zlib.crc32(head + payload) != crc:
            raise ProtocolError("response CRC mismatch")
        return status, payload

    def _command(self, cmd: int, payload: bytes = b"") -> bytes:
        self._send(cmd, payload)
        status, resp = self._recv()
        if status != 0:
            raise DeviceError(status)
        return resp

    # -- commands ----------------------------------------------------------

    def identify(self) -> DeviceId:
        resp = self._command(CMD_ID)
        if len(resp) != 16 or resp[:4] != b"PLG1":
            raise ProtocolError(f"unexpected ID response: {resp!r}")
        fw, ch, _pad = struct.unpack_from("<HBB", resp, 4)
        max_words, base = struct.unpack_from("<II", resp, 8)
        return DeviceId(fw_version=fw, channel_count=ch,
                        max_words=max_words, base_clock_hz=base)

    def status(self) -> DeviceStatus:
        resp = self._command(CMD_STATUS)
        if len(resp) != 24:
            raise ProtocolError(f"unexpected STATUS response: {resp!r}")
        st, err, ch, init = struct.unpack_from("<BBBB", resp, 0)
        ev, words, hz, plays, crc = struct.unpack_from("<IIIII", resp, 4)
        return DeviceStatus(state=st, last_error=err, channel_count=ch,
                            initial_state=init, event_count=ev,
                            word_count=words, sample_clock_hz=hz,
                            plays_completed=plays, payload_crc32=crc)

    def upload(self, wf: PlwWaveform,
               progress=None) -> None:
        wf.validate()
        self._command(CMD_UPLOAD_BEGIN, wf.header_bytes())
        payload = wf.payload_bytes()
        for off in range(0, len(payload), UPLOAD_CHUNK):
            self._command(CMD_UPLOAD_DATA, payload[off:off + UPLOAD_CHUNK])
            if progress:
                progress(min(off + UPLOAD_CHUNK, len(payload)), len(payload))
        self._command(CMD_UPLOAD_END)

    def play(self) -> None:
        self._command(CMD_PLAY)

    def stop(self) -> None:
        self._command(CMD_STOP)

    def clear(self) -> None:
        self._command(CMD_CLEAR)
