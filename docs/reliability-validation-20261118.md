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

### Observed finalization result — 2026-11-19

The second four-hour run used the same 1024-sample, 48 kHz candidate and
independent asynchronous, memory-locked RR9 reference clients. Before recording,
it verified an active owned hardware clock, briefly quiesced only the owned Live
engine, applied the bounded RR10/RR9 grants as a batch, and resumed the engine.
This avoided the sequential-regrant failure in bounded qualifications. It is a
private experimental transition, not an accepted startup implementation.

Both references completed 14,400 clean steady seconds. The finalized mono 24-bit
recording contains 14,413.248 seconds of audio; all 14,407 checked whole-second
windows are clean. All 240 hardware inquiries succeeded, and the native set
contains the expected 1,680 positive-duration MIDI notes.

**Full acceptance failed during Stop.** The independently observed hold interval
captured a real return-signal gap and frame-clock discontinuity. Hardware errors
increased from 144 to 145 and Live errors from 433 to 440; the reference clients'
own error counts stayed zero. Startup calibration had produced one shared-driver
notification in each reference, so acceptance compared subsequent measurement
and hold rows with each reference's own second-20 baseline. New reports and the
measured signal loss failed that gate. Clean saved content does not override it.

The guard stopped only its owned measurement, saved the test set, and restored
all 15 experimental application threads to ordinary scheduling before removing
the reference clock. The failed status, raw observations and stopped native
project were preserved and backed up. No long audio trial is running, and the
once-only checkpoint is disabled with no next run time.

A short display-off/on comparison without a transport change stayed clean. A
separate 22-second native recording reproduced a return gap and increased errors
when Stop was clicked without waking or focusing the display. Read-only thread
timing sampled a file flush and increased audio-callback CPU time near that
event, with little measured run-queue delay. These observations narrow the next
bounded comparisons; they do not establish a filesystem, scheduler, Max device,
or display cause. An external Windows read initially returned a sharing violation
for Live-held recording files. Closing the saved owned set and reopening it
released those handles and allowed the read, so a persistent filesystem
permission failure was not demonstrated. Repeated short recording/Stop/Save
cycles after that fresh reload stayed clean, including bounded user-mode CPU
sampling of the owned main and audio-callback threads. This suggests session
state as a comparison target, but does not establish a cause or certify a fix.

The normal launch profile remains unchanged. Native reopen/export acceptance
for a passing sustained candidate and a guarded persistent scheduling helper
remain gated on an actual full pass. Earlier failed trials retain their failed
status, and the original rare steady-state dropout remains unexplained. Code CI
success is separate from audio acceptance.

### Scheduling transition follow-up

A later bounded comparison stopped during setup, before recording: the system
RTKit daemon exited on SIGKILL while granting the third application thread.
Live survived. Two grants had been acknowledged, but the third had already taken
effect before its D-Bus reply was lost. The caller's cleanup removed that
unacknowledged grant. The private batch now checks all 15 snapshotted roles on
failure, and a controlled test discarded the reply after a real third grant.
It verified all 15 threads ordinary before resuming Live and before removing the
reference clock. This hardens the experiment; it is not a persistent helper or
complete validation of every possible late-reply case.

The normal D-Bus activation restored RTKit without a configuration change.
Disposable scheduling controls then exposed a repeatable distinction on this
host, running kernel `7.2.13-200.fc44.x86_64` and RTKit `0.11-70.fc44`:
when priority was granted to a waiting child, both sleep orders completed nine
35 ms realtime CPU bursts. When granted to a running child, sleeping 200 ms
while still RR9 completed all nine bursts, but sleeping only after demotion to
ordinary scheduling ended in SIGKILL after several bursts. All children used the
same 200000 microsecond hard budget. A second implementation reproduced the
running-thread distinction. No budget was increased.

The [Linux scheduler](https://github.com/torvalds/linux/blob/master/kernel/sched/rt.c)
resets its realtime timeout counter on a realtime wakeup.
[RTKit 0.11](https://github.com/heftig/rtkit/blob/v0.11/rtkit-daemon.c)
temporarily promotes its running request handler and then demotes it before
returning to its event loop. A subsequent read-only kernel trace captured
`SIGKILL` with `SI_KERNEL` for the disposable child in
`posix_cpu_timers_work`. The child completed six bursts in the ordinary-sleep
case and the paired realtime-sleep control completed all nine. Together with
the child's fixed `RLIMIT_RTTIME`, this attributes the reproduced kill to
Linux's realtime CPU limit. The earlier RTKit and Live exits and the Stop audio
dropout remain unresolved. The standalone
[comparison procedure](../validation/README.md#realtime-budget-transition-comparison)
preserves both outcomes and identifies failed/refused requests as inconclusive.
It grants priority only to its own new diagnostic children and is never invoked
by the normal launcher or CI.

A corrected bounded audio sequence separately finalized two native recordings
while playback continued, then stopped playback; both cycles remained clean.
A subsequent combined recording/playback Stop also stayed clean. Transport
button states, finalized WAV headers and stable file sizes prove that Record
actually ended before the separate playback Stop. Hardware/Live/reference
counters stayed at 205/850/0/0. An earlier sequence with an unintended preliminary
control hit its time bound and remains an incomplete attempt. These short results
do not overturn the failed four-hour finalization gate or justify another long
trial without a concrete audio diagnosis. The normal profile is unchanged.

### Ordinary scheduling recording failure

A bounded recording test captured a dropout about 11 seconds after Record,
before any Stop or Save action. Live used ordinary scheduling at 1024 samples
and 48 kHz, and the independent asynchronous reference clients used RR9.
The observer recorded 1024 consecutive zero samples and a frame-clock jump.
The source stayed continuous across the event, and the finalized native WAV
also contained a discontinuity near second 10.

PipeWire profiling placed the missed cycle in Live's processing path. The node
woke 6.10 ms after the graph signaled it and took a further 22.03 ms to report
completion, for 28.13 ms against a nominal 21.33 ms cycle. These are elapsed
times, which can include waits as well as CPU work. Both the hardware driver
and Live error counters increased. The profile identifies the missed deadline
during recording. The earlier dropout at Stop remains unresolved.

A subsequent bounded comparison moved only Live's PipeWire callback to RR9,
keeping its 14 audio workers at ordinary priority. The two reference threads
used the same RR9 policies as before. The comparison failed about 6.18 seconds
after Record, when the hardware and Live error counts increased. Live then
exited with code 137 before the planned Stop. The session supervisor cleaned up
and the temporary grants ended. RTKit remained active. This result rules out
the callback-only profile as an accepted candidate. The source of this SIGKILL
and the earlier failure at Stop remain unresolved.

Two short comparisons tested the owned set's Max SignalAnalyzer enabled and
bypassed, then reversed the order. Live used ordinary scheduling and both
independent reference threads used RR9. With the analyzer enabled in the first
pair, the observer captured 1024 consecutive zero samples and a frame-clock
jump before Record. The guard stopped that trial. Both bypassed recordings
and the enabled recording in the reversed pair completed Record, Stop, and
Save. All 123 checked native PCM windows across the three finished takes
were clean. Two Live errors in the reversed bypassed trial preceded the
steady baseline and did not recur in its measured interval.

The comparison did not reproduce the same fault consistently enough to
attribute it to the analyzer. Worker timing was retained around Record for
all 14 AudioCalc threads in both reversed trials, providing clean reference
captures for a future fault. The analyzer's original state was restored in
the saved test set. Sustained audio acceptance remains failed.

The normal hardware graph also recorded Live and driver errors while transport
was stopped and the generated source and observer were absent. The controlled
idle comparison recorded five new Live errors with the analyzer bypassed and
three after restoring it. Bypass did not eliminate the idle failure. A matched
cycle in a separate idle trace took 11.45 ms from signal to wakeup and 10.47 ms
from wakeup to finish, exceeding the nominal 21.33 ms period. The surrounding
scheduler samples include time on either side of that cycle.

The earlier terminal launch inherited the agent's CPU group with weight 10
under the desktop application group. The same saved owned set was reopened
through the normal launcher in a separate desktop application scope, with
ordinary scheduling. Its first 2700-cycle idle check recorded no errors; the
second recorded two Live errors and one driver error. A 75-second recording
then completed through Stop and Save, with 71 clean native PCM windows. The
desktop scope eliminates the inherited weight difference from later tests
but did not eliminate idle errors. Neither change passed sustained acceptance.

With both reference clients and Live at ordinary priority, a temporary
asynchronous Live node failed about 47 seconds after Record. The observer
captured 2048 consecutive zero samples. The source remained continuous, and
Live's error counter increased from 6 to 7 while hardware and reference
counters held steady. The finalized 48.576-second native WAV also failed its
tone and phase checks around seconds 45–46. The asynchronous launch was
reverted after saving the failed take.

A synchronous control with the same source, observer, buffer, and test
procedure completed Record, Stop, and Save. All 72 checked native PCM windows
were clean and the measured error counters held steady. This pair rules out
the tested asynchronous setup for promotion. It leaves the intermittent
failure under the normal synchronous launch unresolved.

The host was on AC power with a 1.7 GHz CPU ceiling and turbo disabled in
power-saver mode. A temporary desktop performance hold raised the ceiling to
4.7 GHz and enabled turbo. The same synchronous recording, Stop, and Save
check completed with unchanged error counters and 72 clean native PCM
windows. Live's 99th-percentile graph signal-to-finish time fell from
3.81 ms to 1.33 ms across approximately 3600 recorded cycles per mode. Both
short synchronous recordings stayed inside the 21.33 ms cycle budget. The
timing margin improved during the temporary hold. Causality for the previous
dropouts remains unresolved. The hold was released and the original desktop
power state verified.

A follow-up reversed the order on the same synchronous Live session and used
independent RR9 source and observer threads in both runs. The performance hold
completed Record, Stop, and Save with 72 clean native PCM windows and unchanged
error counters. Live finished within 3.94 ms on all 3617 matched recording
cycles. After releasing the hold, the power-saver control stopped before Record.
The source signal stayed continuous, and the observer captured zero samples
and frame-clock jumps while Live and hardware errors increased. The comparison
qualifies the performance hold for further testing. Sustained acceptance and
the cause of the earlier recordings' dropouts remain open.

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
