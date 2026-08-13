# Timing and cycle accounting

## Clock chain

```
12 MHz crystal -> PLL (1500 MHz / 6 / 2) -> clk_sys = 125 MHz
clk_sys / clkdiv (integer D)            -> PIO clock
5 PIO cycles                            -> 1 waveform sample
```

- `sample_clock_hz = 125_000_000 / (5 * D) = 25_000_000 / D`
- D = 1 gives the 25 MHz base timebase (40 ns per sample).
- Slower sample clocks are supported for any `sample_clock_hz` that
  divides 25 MHz with `D <= 65535` (25 MHz, 12.5 MHz, 5 MHz, 1 MHz,
  ... down to ~381 Hz). The divider is always an integer; fractional
  PIO dividers are rejected because they dither the clock and would
  introduce cycle-to-cycle jitter.

**Determinism vs accuracy.** Once playback starts, edge placement is
determined solely by the PIO instruction stream and the FIFO/DMA data
path; interrupts, USB traffic and CPU load cannot move an edge by even
one cycle. Absolute frequency accuracy is a separate property: it
equals the board's crystal accuracy (roughly +/-30 ppm on a Pico W),
so "25 MHz" is 25 MHz +/- crystal tolerance, but every interval is an
exact integer number of those real oscillator cycles.

## The PIO program

One sample = exactly **5 PIO cycles**. Running the PIO 5x faster than
the sample clock is what allows back-to-back edges on consecutive
samples (40 ns apart at the full rate) despite the per-event
instruction overhead.

```
.wrap_target
    out x, 24        [1]  ; (a) 2 cycles: x = N - 1
next:
    jmp x-- delay         ; (b) 1 cycle: falls through when x == 0
    out pins, 8      [1]  ; (c) 2 cycles: drive new state
.wrap
delay:
    jmp next         [3]  ; (d) 4 cycles
```

Every FIFO word encodes one event: `(state << 24) | (N - 1)`, with
`N >= 1` the hold time in samples. The OSR shifts right with autopull
at 32 bits, so `out x, 24` consumes the delay field and `out pins, 8`
consumes the state field of the same word.

### Per-event cycle count

- `N == 1`: (a) 2 + (b) 1 (fall through) + (c) 2 = **5 cycles**
- `N >= 2`: (a) 2 + (N-1) loop passes of (b taken) 1 + (d) 4 = 5 each
  + final (b fall-through) 1 + (c) 2 = 2 + 5(N-1) + 3 = **5N cycles**

So event k occupies exactly `5 * N_k` PIO cycles, with the pin update
in the final cycle of the event. Concretely, the `out pins` of event k
executes at PIO cycle `5 * (N_1 + ... + N_k) - 2` counted from SM
enable, and the new level is visible on the GPIO pad one cycle later.
The `-2`/`-1` offset is the same constant for every event, therefore:

> Edge-to-edge spacing between event k and event k+1 is exactly
> `5 * N_{k+1}` PIO cycles = `N_{k+1}` samples. No off-by-one, no
> drift, no accumulation.

This is verified instruction-by-instruction by the host-side simulator
(`picowave/piosim.py`, exercised in `host/tests/test_piosim.py`),
which steps the four instructions with the documented delay fields and
asserts the exact cycle of every pin change for the canonical vector,
back-to-back N=1 events, counter-range delays and randomized vectors.

### Why the FIFO can never underrun

The worst case is a stream of N=1 events: one 32-bit word consumed
every 5 system clock cycles (at D=1). The RP2040 DMA sustains one
32-bit transfer per system clock cycle and the channel is configured
with high bus priority; the TX FIFO is joined to 8 entries and
pre-filled before the SM is enabled. The DMA therefore always stays
ahead of the SM, and the SM never stalls mid-waveform. (At D>1 the
margin only grows.)

### Long delays

The delay field is 24 bits, so a single word covers `N` up to
2^24 samples (671 ms at 25 MHz). At **upload time** (never during
playback) the firmware splits longer host delays into filler words
that re-drive the current state (a no-op on the pins) followed by the
remainder, preserving the exact total sample count. Host-side `delay`
is a u32, so one host event covers up to ~171 s at 25 MHz; longer
holds can chain multiple no-change events.

## Start, end and replay

- **t = 0**: the initial state is driven on the pins while arming (and
  again on every restart) via the SM's own `out pins, 8` path, so all
  8 bits are applied simultaneously. The SM is then enabled with the
  FIFO pre-filled; the first event's delay counts from SM enable.
- **End of waveform**: the FIFO drains and the SM stalls forever on
  `out x, 24` with the last event's state still driven. Outputs hold
  that final state indefinitely. Completion is detected by the CPU as
  DMA-done + FIFO-empty + TXSTALL, i.e. strictly after the final edge.
- **Replay** (button or host `PLAY`): the engine is halted, the DMA
  channel is reconfigured to the start of the unchanged word buffer,
  SM/FIFO/shift counters/clkdiv are fully reset, the initial state is
  re-driven, the FIFO is pre-filled and the SM re-enabled. Every replay
  therefore reproduces the identical cycle-exact waveform. The latency
  from button press to waveform start is *not* specified (it includes
  debounce and software); everything after t=0 is.

## RAM budget and capacity

| item | size |
|---|---|
| playback word buffer | 49,152 words = 192 KiB (static) |
| everything else (stack, USB, protocol) | < 40 KiB |

- **Event encoding**: up to ~49k transitions per waveform; duration is
  effectively unbounded (each word covers up to 671 ms; a waveform of
  49k max-delay words lasts > 9 hours at 25 MHz).
- **Raw 8-bit samples for comparison**: 264 KiB SRAM at 25 MSa/s would
  hold only ~10.5 ms. This is why the transition encoding is the only
  playback format.
