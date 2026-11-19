# Audio isolation diagnostics

These optional tools measure a disposable validation project. They do not change
the normal launch profile, grant realtime priority, or connect audio ports.

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
audio server. The monitor uses a bounded, prefaulted observation array and
reports whether its measurement memory was locked. Its audio callback performs
no allocation, locking or file I/O.

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

The optional `--hold` argument emits `measurement_complete` after the requested
observations, then retains its ports until SIGTERM or another 30 seconds. This
allows the caller to stop native recording before removing the observer changes
the graph. The monitor also enforces a wall-clock limit of the requested duration
plus 60 seconds. Clip-edge fades must be disabled for the continuous reference:
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
