# USB host protocol

Transport: USB CDC (virtual serial port, Raspberry Pi VID `0x2E8A`).
USB is used only for control and upload; it plays no part in playback
timing. Both directions use the same framed binary format
(little-endian):

```
sync(1) | cmd_or_status(1) | len(2) | payload(len) | crc32(4)
```

- sync: `0xA5` host -> device, `0x5A` device -> host
- crc32: CRC-32 (IEEE, zlib) over `cmd/status + len + payload`
- max payload: 2048 bytes
- Every request produces exactly one response. Response `status = 0`
  is success; nonzero is an error code (below). A partial request
  frame times out after 500 ms and is discarded.

## Commands

| cmd | name | request payload | response payload (on OK) |
|---|---|---|---|
| 0x01 | ID | none | `"PLG1"`, fw_version u16, channels u8, pad u8, max_words u32, base_clock_hz u32 |
| 0x10 | UPLOAD_BEGIN | 24-byte `.plw` header | none |
| 0x11 | UPLOAD_DATA | raw event bytes (any chunking) | none |
| 0x12 | UPLOAD_END | none | none |
| 0x20 | STATUS | none | see below |
| 0x21 | PLAY | none | none |
| 0x22 | STOP | none | none |
| 0x23 | CLEAR | none | none |

STATUS response payload (24 bytes): state u8, last_error u8,
channels u8, initial_state u8, event_count u32, word_count u32,
sample_clock_hz u32, plays_completed u32, payload_crc32 u32.

`payload_crc32` echoes the armed waveform's CRC, so the host can prove
the stored waveform is unchanged between replays; `plays_completed`
counts finished playbacks since boot.

## Error codes

| code | name | meaning |
|---|---|---|
| 1 | BAD_CMD | unknown command |
| 2 | BAD_CRC | request frame CRC mismatch |
| 3 | BAD_STATE | command not valid in current state |
| 4 | BAD_FORMAT | header magic/version/fields invalid |
| 5 | TOO_BIG | waveform exceeds the playback buffer |
| 6 | BAD_RATE | unsupported sample_clock_hz |
| 7 | UPLOAD_SEQ | DATA/END out of order or wrong total size |
| 8 | BAD_LENGTH | frame payload length invalid |
| 9 | PAYLOAD_CRC | uploaded payload CRC mismatch |
| 10 | BAD_DELAY | event with delay == 0 or state > 0xFF |

## Device state machine

```
IDLE --UPLOAD_BEGIN--> RECEIVING --UPLOAD_END ok--> LOADED
RECEIVING --any upload error--> ERROR
LOADED/COMPLETE --PLAY or button--> PLAYING --finished--> COMPLETE
PLAYING --STOP--> LOADED (outputs return to initial_state)
any state except PLAYING --UPLOAD_BEGIN--> RECEIVING (replaces waveform)
any --CLEAR--> IDLE (outputs all low)
```

- UPLOAD_BEGIN is rejected while PLAYING (STOP first). It immediately
  unarms/replaces the previous waveform.
- Events are validated and converted to PIO words during upload;
  UPLOAD_END verifies the payload CRC before arming. On any failure
  the device enters ERROR (no waveform armed) and reports the code in
  `last_error`.
- PLAY is valid in LOADED/COMPLETE only; pressing the hardware button
  is equivalent to PLAY (and is likewise ignored in other states,
  including during playback).
