# Waveform formats

## Event semantics (both formats)

A waveform is an initial output state plus an ordered list of events:

```
(delay_in_samples, new_output_state)
```

- At `t = 0` the outputs drive `initial_state`.
- Event k holds the **current** state for `delay_k` samples and then
  drives `state_k`. The first event's delay therefore counts from
  playback start: `initial_state` is visible for exactly `delay_1`
  samples before the first edge.
- Edge k occurs at `t = delay_1 + ... + delay_k` samples.
- `delay >= 1` always; `delay = 0` is invalid and rejected. Two edges
  can be as close as 1 sample (40 ns at 25 MHz).
- After the last event the outputs hold `state_last` until the
  waveform is replayed, stopped (returns to `initial_state`) or
  cleared (all low).
- A no-change event (`state == current state`) is legal and simply
  extends the hold time; the firmware itself uses this to split long
  delays.

## Binary `.plw` file / upload format

Little-endian throughout. Header (24 bytes):

| offset | size | field | value |
|---|---|---|---|
| 0 | 4 | magic | `"PLW1"` |
| 4 | 2 | version | 1 |
| 6 | 2 | flags | 0 |
| 8 | 4 | sample_clock_hz | must divide 25,000,000 with divider <= 65535 |
| 12 | 1 | channel_count | 8 |
| 13 | 1 | initial_state | output state at t = 0 |
| 14 | 2 | reserved | 0 |
| 16 | 4 | event_count | >= 1 |
| 20 | 4 | payload_crc32 | CRC-32 (IEEE, zlib) of the event payload |

Followed by `event_count` events of 8 bytes each:

| offset | size | field |
|---|---|---|
| 0 | 4 | delay (samples, u32, >= 1) |
| 4 | 4 | state (u32; bits [7:0] used, others must be 0) |

The device rejects (rather than reinterprets) wrong magic, unknown
version, nonzero flags/reserved, unsupported channel count, invalid
sample clock, zero delays, out-of-range states, size overflow and CRC
mismatch. `version`, `flags` and the u32 `state` field leave room for
future extensions (more channels, new event types) without breaking
old parsers.

## Text format

Human-editable; compiled to `.plw` with `picowave build`:

```
# comment
clock 25000000     # optional, default 25 MHz
initial 0x00
10   -> 0xFF       # hold 10 samples, then drive 0xFF
5000 -> 0x00
```

Numbers accept decimal, hex (`0x..`) and binary (`0b..`). `clock` and
`initial` must precede the first event.
