# Reliability validation — 2026-11-18

Implementation: `f7fd956`. The pinned application/runtime baseline remains the
one recorded in [component validation](component-validation-20261118.md).

## Reboot and reconnect

The host booted at 08:28:40 local time. A subsequent installed desktop
**Start with Bome** launch opened the configured project and established the
exclusive route automatically. Live reported an authorized license after the
reboot. The Launchpad appeared at ALSA `16:0`, replacing its previous `20:0`
address; discovery selected it without a fixed client number. MIDI Through
was available without loading VirMIDI.

The physical unplug/replug test exposed a missing subscription: Wine retained
Bome's MIDI input but did not reconnect it to the returned Launchpad. The new
`--reconnect` operation restored that subscription into the existing owned
input. A hardware inquiry response then traversed Bome again. Under the updated
supervisor, reproducing the same lost subscription triggered automatic recovery
within 2.06 seconds. No second cable action was required for that repair check.

Automatic input repair is armed only after the session first verifies a complete
project route. It requires one owned open Bome input and its existing MIDI Through
output. It does not open a new application port or rescan Wine's device list.
Hardware absent at startup or hardware that Wine cannot enumerate can still
require saving and restarting the full session.

## Recovery and CI

All fourteen entries in the previous recovery evidence checksum manifest
verified. Thirteen backed-up project files were copied to an isolated restore
directory and compared byte for byte. The source bundle cloned successfully at
`f1fa5b2`. Native Live opened the restored recording files from that directory
and exported ten seconds of the expected 440 Hz signal; measured tone energy
exceeded 0.99999995. The running installation and original project were preserved.
This verifies source/project restoration, not a new full-prefix rollback or an
off-machine backup.

The reconnect implementation passed 138 isolated regressions and ShellCheck.
It was published to `main`, and
[GitHub verification passed](https://github.com/timcisneros/waydaw/actions/runs/44352541146),
including native helper build reproducibility and KWin compatibility checks.

## Sustained workload — stability gap under investigation

A dedicated **Soak Validation** project records generated audio at 48 kHz,
including processing through the bundled Max SignalAnalyzer. MIDI note
sequences are replayed into the Ableton bus, while separate hardware inquiries
check the physical Launchpad → Bome → MIDI Through path every minute.

The measurement client compares captured 440 Hz and 997 Hz tones once per
second, counts JACK xruns, and records signal gaps, CPU use, and phase delay.
An initial twenty-second calibration at 1024 samples had zero xruns and preserved
the generated signal. Its software graph delay was 1024 frames (21.33 ms at
48 kHz), excluding physical converter latency.

A longer 1024-sample test exposed steady-state gaps of roughly two buffers
(about 43 ms), with corresponding JACK xruns. PipeWire reported errors on the
Ableton node while the probe node's error count remained zero. Temporarily
raising only the owned audio threads' normal scheduling priority to nice -10
did not remove the gaps; that trial ended with the process, and no priority
change was retained.

A separate 2048-sample candidate, still using ordinary scheduling, also
encountered a gap after about six minutes and stopped automatically. Neither
ordinary-scheduling buffer setting has passed sustained acceptance.

A controlled follow-on trial applies RTKit round-robin scheduling only to the
owned audio-processing threads: AudioCalc priority 10 and the PipeWire data loop
priority 9, with the daemon's bounded CPU-time budget. That trial ran for about
31 minutes without a captured signal gap or phase discontinuity, then stopped on
two shared hardware-driver xrun notifications. Ableton's own error counter did
not increase. Checks of the saved recording around the event also stayed clean.

The user reported using volume keys near that event. Replaying the desktop
volume actions in a separate silent test produced neither the notification nor
signal loss, so the cause is unconfirmed. PipeWire's JACK implementation derives
this callback from the [shared driver's counter](https://github.com/PipeWire/pipewire/blob/1.6.11/pipewire-jack/src/pipewire-jack.c#L1965).

The refined measurement began at 10:19:57 local time and stopped automatically at
12:26:32, after about two hours and six minutes. The first failure included a
2048-sample gap in the captured return, a frame-clock discontinuity, and increased
error counts on both Ableton and the measurement client. The saved native
recording also contains a discontinuity around that event. All 125 hardware MIDI
inquiries succeeded, but sustained audio acceptance failed.

The measurement client was still explicitly using ordinary scheduling while
Ableton's selected audio threads had realtime priorities. Its contribution to
the failure needs isolation before attributing the cause to Ableton. Volume-key
causality remains unconfirmed. Short CPU-load comparisons with and without
realtime probe scheduling did not reproduce the failure. The pending final check
was cancelled when this failure was inspected; the stopped attempt and its
evidence were preserved. The temporary priorities on the matching experimental
threads were then restored to ordinary scheduling.

The monitor records frame-clock continuity, owned-client errors, shared-driver
reports, and audio-control events separately. It stops on measured signal/clock
loss or owned-client error increases. Shared-driver notifications also remain in
the final acceptance check and require review. The normal launch profile remains
unchanged pending sustained acceptance and a guarded persistent scheduling
implementation.

### Isolating the measurement path

New capture-only diagnostics and a native playback/resampling fixture separate
the signal source from its observer. Seven injected-fault meter tests cover
signal loss, channel loss, phase continuity and frame-clock handling. The full
isolated regression suite passed 145 tests.

A controlled 200 ms pause of the synchronous observer caused a hardware xrun.
The same pause with asynchronous observation caused no hardware or Live errors;
the native recordings remained clean in both cases. This confirms that the old
measurement topology could influence the graph. It does not establish the cause
of the earlier unprovoked recording failure. See the
[diagnostic procedure](../validation/README.md).

The unchanged normal launch at 1024 samples was then tested with native playback
and the isolated observer. Within 30 seconds it missed an output deadline:
hardware and Live error counts increased, while the observer's error count
stayed zero. Native internal resampling stayed clean. The output stability gap
therefore remains reproducible without the external signal generator.

A subsequent, temporary 1024-sample trial applies RR10 to owned AudioCalc threads
and RR9 to the owned PipeWire data loop, with a 200000 microsecond realtime limit.
It completed a three-minute qualification with zero driver/client error increases
and clean capture/native content. Sustained acceptance remains pending. These
priorities have not been added to the normal launcher or promoted as a profile.

A split-source ASIO input/output qualification then completed 60 steady seconds
with verified RR9 asynchronous source and observer clients. Both reference
streams stayed continuous, 72 finalized native-recording windows were clean,
and seven MIDI notes plus a Launchpad/Bome inquiry were captured successfully.
Live writes its recording payload before finalizing the WAV header, so the
bounded guard checks the known active PCM payload separately from final WAV
validation. This qualification validates the corrected test setup; a complete
sustained result is still required.

The corrected four-hour run completed 14,400 clean steady seconds in each
independent reference client. Its saved mono 24-bit recording is 14,418.837
seconds long; all 14,412 checked whole-second windows are clean. The native set
contains the expected 1,680 positive-duration MIDI notes and all 240 hardware
inquiries returned through Bome.

Full acceptance nevertheless failed at finalization: hardware errors increased
from 90 to 92 and Live errors from 93 to 105 between the final steady snapshot
and the counter read after Stop/Save. Neither reference's client-error count
increased. The original failed status is preserved. The former hold mode kept
ports alive but stopped publishing observations at the requested endpoint, so
those reports cannot yet be attributed precisely. Both diagnostic clients now
continue publishing separately marked hold observations, with regression tests
for the protocol. Clean four-hour content does not override the failed final gate.

A subsequent bounded comparison did not reach measurement: sequentially
reapplying the temporary RTKit priorities caused Live to exit with code 137.
The saved owned project had already been backed up and verified. That private
regrant action was disabled, and Live was reopened through the unchanged normal
desktop launcher with ordinary scheduling. The exact kill cause and a safe
scheduling transition need validation before a persistent helper is accepted.
The [Linux realtime CPU limit](https://man7.org/linux/man-pages/man2/getrlimit.2.html)
can terminate a realtime task that consumes its budget without blocking; this
remains a hypothesis for the observed exit, rather than an established cause.

The measurement confines generated tones to Live and its capture ports. A
zero-only observer port keeps the hardware audio clock active without sending
test tones to the speakers. Separate source and observer clients now report
their own continuity and use verified scheduling; the ASIO input workload does
not depend on an ordinary-scheduled combined generator/observer. No microphone
input is used. Native recording growth is
tracked across all project recording files: Live can preallocate its next-take
file before Record starts. A prior watcher attempt that selected an empty
next-take file was stopped, corrected, and preserved with its evidence.

The runner stops its measurement if the guarded application, session, or owned
project changes. A temporary sleep inhibitor lasts only for the test. It leaves
Ableton open, saves the owned project when it can verify it, and removes its
own audio/MIDI clients when finished. It does not close another project.

Evidence, source and build provenance are under
`~/.local/state/waydaw/reliability-validation-20261118/`. The corrected run's
status is `native-isolation/io-soak-status.json` there. The root `soak-status.json`
and earlier attempt directories preserve the prior failed measurement.
No representative third-party plugin collection or external audio interface
was available for this test. Those combinations and physical round-trip latency
remain separate acceptance work when that production equipment is available.
