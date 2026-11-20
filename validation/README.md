# Audio isolation diagnostics

The optional audio tools measure a disposable validation project. They do not
change the normal launch profile, grant realtime priority, or connect audio ports.
The separate scheduling comparison below explicitly grants priority only to
new disposable diagnostic children.

The earlier measurement client generated the input and captured Live's output in
the same synchronous graph. A delayed measurement process could therefore affect
the signal being tested. Native playback and native resampling remove the
external generator from that path. A separate asynchronous observer measures the
output. [PipeWire's scheduling documentation](https://docs.pipewire.org/page_scheduling.html)
explains that an asynchronous node does not hold up completion of its peers.
This identifies a measurement risk; it does not establish the cause of an earlier
recording failure.

## Build and verify

Install a C compiler and JACK development headers, then build:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror validation/audio-monitor.c \
  $(pkg-config --cflags --libs jack) -lm -o /tmp/waydaw-audio-monitor
cc -std=c11 -O2 -Wall -Wextra -Werror validation/audio-source.c \
  $(pkg-config --cflags --libs jack) -lm -o /tmp/waydaw-audio-source
python3 -m unittest discover -s tests -p test_audio_meter.py -v
```

The tests inject buffer loss, a phase jump at a window boundary, a clock skip,
valid clock wraparound, a nonfinite sample, and channel loss without starting an
audio server. Separate protocol tests use a fake JACK client to verify completion
ordering, continued hold observations and reports after the requested endpoint.
Run them with `python3 -m unittest discover -s tests -p test_audio_diagnostic_protocol.py -v`.
The monitor uses a bounded, prefaulted observation array and
reports whether its measurement memory was locked. Its audio callback performs
no allocation, locking or file I/O.

## WineASIO sample position

The optional clock test exercises the actual ASIO callbacks and
`GetSamplePosition` in the 64-bit WineASIO 1.3.0 build. Use a disposable Wine
prefix, a private Wine runtime, and a private PipeWire server with a timer
driver at 1,024 frames and 48 kHz. Mark the JACK client with
`PIPEWIRE_PROPS='{ node.always-process = true }'` so the timer advances without
hardware ports. Keep WineASIO hardware autoconnection and JACK server
autostart off.

Use two scratch source trees from [WineASIO commit b5e6681](https://github.com/wineasio/wineasio/tree/b5e668103ad13e6f51f4118ed7090592213e5ca2).
Apply [the candidate patch](wineasio/sample-position.patch) to one tree.
Run `python3 validation/wineasio/seed-clock.py /path/to/scratch/asio.c` on
each tree after applying the patch. It lets the test host initialize the
counter two callbacks before each boundary. Build and register each driver
in the disposable environment. Build the Windows test host with MinGW.

```sh
x86_64-w64-mingw32-gcc -std=c17 -O2 -Wall -Wextra -Werror \
  validation/wineasio/clock-host.c -lole32 -luuid -o /tmp/wineasio-clock-host.exe
```

Run the executable with `basic` and `time` modes and starting positions
`2147481600` and `4294965248` for each mode. Pass `0` to check an unseeded
build. It prints actual and expected positions, then verifies that a second
Start resets the same driver instance to zero. Exit status 2 reports a
boundary mismatch. Any other nonzero status indicates a setup, restart or
runtime error. The seed script is for disposable builds only.

## Controlled comparison

1. In an owned test project, loop known 440 Hz audio, optionally with a 997 Hz
   second tone, through the intended Live effects. Record the output natively
   with Resampling. Mute the recording track and turn its input monitoring off
   to prevent feedback.
2. Disconnect only that test application's physical output links, preserving
   their exact endpoints for cleanup. The monitor's `clock_silence` port contains
   zeros and can anchor the graph to the hardware clock without audible tones.
3. Start the observer with a fixed duration and explicit asynchronous scheduling:

   ```sh
   PIPEWIRE_PROPS='{ node.async = true }' \
     pw-jack /tmp/waydaw-audio-monitor 60 > capture.jsonl
   ```

   Connect the application's two output channels to `capture_L` and `capture_R`.
   Verify `node.async` and negotiated link properties with `pw-dump`. Record the
   actual processing-thread policy and priority. A caller that uses RTKit must
   check process/thread identity and bound the realtime budget; this tool does
   not grant that privilege itself.
4. After a clean startup allowance, briefly pause and resume only the owned
   observer process, retaining its process identity throughout. Compare its clock
   and signal measurements with the independent native recording. A synchronous
   control can establish whether that topology couples observer delays back into
   the application. Keep injected faults separate from unprovoked failures.
5. Stop and save only the owned project, remove only owned clients, and restore
   its original links. Compare the native recording around the injection with
   adjacent clean windows before drawing a conclusion.

Each JSON observation covers one second of captured samples, with graph-frame
and monotonic timestamps, callback spacing, signal purity, channel difference,
zero runs and phase continuity. Phase checks ignore absent carriers. The shared
driver-notification count is sampled by the reader and is not an application-only
error count. Missing observer callbacks also make captured-sample duration differ
from elapsed wall time; preserve both time bases.

To align a failure with a PipeWire profiler or scheduler trace, use
`first_clock_discontinuity` for the first skipped or repeated frame in a
window and `longest_callback_interval_end` for the two callback timestamps
bounding its largest interval. Each reports the actual and expected 32-bit
graph frames together with the callback timestamps. `longest_zero_run_start`
identifies the first silent sample of the longest left-channel run and the
timestamp of the callback that carried it. A run can begin in an earlier
window. These points locate the observations in the graph; the return
client's latency and graph position still matter when attributing a cause.

The optional `--hold` argument emits `measurement_complete` after the requested
observations, then retains its ports until SIGTERM or another 30 seconds. It
continues publishing observations with `phase: "hold"`; earlier rows have
`phase: "measurement"`. The completion event includes the last measurement's
monotonic timestamp. The final event includes the notification count sampled
before client deactivation. The extra observation storage is bounded and locked
with the measurement storage.

Keep observing while stopping and saving the native recording, and record each
action's monotonic interval and before/after client counters. A clean requested
interval followed by an unexplained final counter increase is an incomplete
acceptance result. A single counter read after several actions cannot identify
which action caused it. Wait for a complete observation after the final action
before removing the clients. This avoids both a blind finalization interval and
port removal changing the graph while native recording is active.

The monitor also enforces a wall-clock limit of the requested duration plus
60 seconds. Clip-edge fades must be disabled for the continuous reference:
the calibration should verify loop boundaries before any fault is attributed.

A short comparison validates the measurement setup. Sustained acceptance still
requires the complete recording workload, stable native content, MIDI routing,
and save/reopen/export verification before a launch profile is promoted.

## ASIO input/output workload

After validating observer isolation with native playback, `audio-source` can
exercise the ASIO input path separately. It emits 440 Hz and 997 Hz tones through
`source_L` and `source_R`. It has no input/capture ports, follows the graph clock,
and reports its own clock/signal continuity. Use it as a separate process from
the observer, verify both clients' actual scheduling and memory-lock status, and
connect its outputs only to the owned test application's inputs. Confirm no
other source, including a microphone, feeds those inputs. The observer's zero
port can keep the real hardware clock active while the application's speaker
links are disconnected. Preserve source faults separately from application and
observer faults. `audio-source` supports the same fixed duration and bounded
`--hold` protocol as the observer.

## Realtime budget transition comparison

This separate Linux diagnostic compares a 200 ms sleep before and after dropping
from RR9 to ordinary scheduling. Each child has a fixed 200000 microsecond
realtime limit and nine 35 ms CPU bursts. The driver verifies the new child's
PID, thread, UID, executable and process birth before granting priority. It
never attaches to Live, accesses a Wine prefix, changes RTKit configuration or
updates a normal launch profile. It requires Python's `dbus` module and an
already running RTKit service.

Build and explicitly run the comparison, using a new evidence directory:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror validation/rt-budget-transition.c \
  -o /tmp/waydaw-rt-budget-transition
python3 validation/rt-budget-transition.py --run \
  --binary /tmp/waydaw-rt-budget-transition --output /tmp/waydaw-rt-transition-running
```

The default grants priority while the child is running. For a separate control,
wait at least 21 seconds between invocations to respect RTKit's request limit,
then repeat with `--promotion waiting` and a different output directory. That
child waits for the parent's command after its grant, waking under realtime
scheduling. Preserve refusals, service disconnects and unexpected exits as
inconclusive attempts rather than recording them as a reproduced kernel pattern.

The driver records both exits, completed bursts, request/CPU timestamps, and
source/binary provenance. `pattern_observed` means the sleep-while-RR control
completed but the sleep-after-demotion comparison received SIGKILL. It does not
establish the sender of an earlier unrelated kill, fix the host scheduler, or
evaluate audio acceptance. A whole pair is bounded; either child is stopped on
controller error. No realtime comparison runs in CI. Its isolated regression
checks verify that an ungranted child times out or exits on closed input without
performing the realtime workload, reject a forged thread ID before any grant,
and verify child cleanup after a failed request.
