# pico_logic_gen

Deterministic logic waveform generator for the Raspberry Pi Pico W
(RP2040): a "reverse logic analyzer". The host uploads a waveform once
over USB; the device replays it with hardware-timed, cycle-accurate
output on 8 GPIOs at a 25 MHz sample timebase. After playback starts,
timing is produced entirely by PIO + DMA: no interrupts, no USB, no
CPU in the loop.

```
Host (picowave CLI)
  | USB CDC (control + upload only)
  v
RP2040 firmware
  |-- .plw event stream --> validated + expanded to 32-bit PIO words
  |-- 192 KiB playback buffer (SRAM)
  |-- DMA (paced by PIO TX DREQ, one shot, no IRQs)
  v
PIO0 SM0 (waveplay program) --> GP0..GP7 @ 25 MHz sample clock
```

## Hardware

| function | pin | notes |
|---|---|---|
| waveform outputs, ch0..ch7 | GP0..GP7 | 3.3 V push-pull, active high |
| replay button | GP15 to GND | internal pull-up, active low, 10 ms debounce |
| status LED | onboard (Pico W) | on = waveform armed |

- Idle / cleared: all outputs driven low. Stopped: outputs return to
  the waveform's initial state. Completed: outputs hold the final
  state.
- All 8 outputs are updated by a single PIO `out pins, 8`, so
  multi-bit transitions are simultaneous by construction.
- Button semantics: pressing it in LOADED/COMPLETE starts playback
  from the beginning; every press replays the identical waveform (the
  buffer is never modified by playback). Presses during playback or
  upload are ignored (the simple deterministic choice). The button is
  a control event only; it never touches PIO timing.

## Timing in one paragraph

The system clock is 125 MHz; the PIO runs at 125 MHz / D (integer D)
and one waveform sample is exactly 5 PIO cycles, so the sample clock
is 25 MHz / D (D = 1 -> 25 MHz, 40 ns). Each event is one 32-bit word,
`(state << 24) | (delay_samples - 1)`, and the PIO program takes
exactly `5 * delay` cycles per event, allowing back-to-back edges one
sample apart. Cycle-to-cycle determinism is structural; absolute
accuracy is the crystal's (~ +/-30 ppm). The full cycle accounting
proof and FIFO underrun analysis is in [docs/TIMING.md](docs/TIMING.md);
the format and protocol are in [docs/FORMAT.md](docs/FORMAT.md) and
[docs/PROTOCOL.md](docs/PROTOCOL.md).

Capacity: ~49k transitions per waveform (192 KiB word buffer).
Duration is effectively unbounded thanks to the transition encoding
(a raw 25 MSa/s sample buffer would cap out at ~10 ms).

## Building the firmware

Requires the [pico-sdk](https://github.com/raspberrypi/pico-sdk)
(tested with 2.1.1, submodules `lib/tinyusb` and `lib/cyw43-driver`
initialised) and `gcc-arm-none-eabi`:

```sh
cmake -B build -DPICO_SDK_PATH=/path/to/pico-sdk   # PICO_BOARD=pico_w default
cmake --build build -j
```

Flash `build/firmware/plg_firmware.uf2` by holding BOOTSEL while
plugging in, or with `picotool load -f build/firmware/plg_firmware.uf2`.
For a non-W Pico build with `-DPICO_BOARD=pico` (the LED is simply
skipped).

## Host tool

```sh
pip install ./host        # installs the `picowave` CLI (pyserial only)
```

```sh
picowave build examples/test_vector.txt -o test.plw   # text -> binary
picowave info test.plw                                # size/duration
picowave sim test.plw --vcd test.vcd                  # edge table + VCD
picowave upload test.plw --play                       # upload (+ start)
picowave status | play | stop | clear | id | ports
```

Programmatic generation:

```python
from picowave import Waveform
w = Waveform(initial=0x00)            # 25 MHz timebase
w.event(10, 0xFF)                     # hold 10 samples, then drive 0xFF
w.square(channel=0, period=10, cycles=100)
w.save("wave.plw")
```

Slower timebases: `Waveform(initial=0, sample_clock_hz=1_000_000)` or
`clock 1000000` in the text format. Any integer divisor of 25 MHz with
divider <= 65535 is accepted; everything else is rejected by both the
host tool and the firmware.

## Validation

- `host/tests/` (run with `pytest`) contains an instruction-level
  simulator of the PIO program that proves the cycle accounting: exact
  edge cycles for the canonical vector, back-to-back 1-sample events,
  square waves, simultaneous multi-bit transitions, 24-bit
  counter-boundary delays and randomized vectors, plus format/CRC and
  text parser tests.
- On hardware, upload `examples/test_vector.txt` and check with a
  scope/logic analyzer against the edge table printed by
  `picowave sim` (edges at samples 10, 20, 120, 157, 5157; 40 ns per
  sample). Press the button repeatedly and diff captures: replays are
  cycle-identical, and `picowave status` exposes `plays_completed` and
  the stored waveform CRC to prove the buffer is unchanged. Hammering
  `picowave status` during playback must not move any edge; USB is not
  part of the playback path.

## Repository layout

```
firmware/    RP2040 firmware (PIO program, DMA engine, protocol)
host/        picowave Python package + tests
examples/    example waveforms (text + generator script)
docs/        TIMING.md, FORMAT.md, PROTOCOL.md
```
