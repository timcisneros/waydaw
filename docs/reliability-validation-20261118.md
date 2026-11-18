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

A separate candidate requests a 2048-sample quantum and preferred ASIO buffer,
using the same ordinary scheduling fallback. This is supplied only to the
validation launch; the normal launch profile remains unchanged pending
acceptance. Its four-hour measurement started at 09:16:14 local time, with a
ten-second startup allowance. The runner stops early if a measured steady
xrun or signal gap appears. This candidate has not yet passed sustained acceptance.

The current probe confines generated tones to Live and its capture ports. A
zero-only port keeps the hardware audio clock active without sending the test
tones to the speakers. No microphone input is used. Native recording growth is
tracked across all project recording files: Live can preallocate its next-take
file before Record starts. A prior watcher attempt that selected an empty
next-take file was stopped, corrected, and preserved with its evidence.

The runner stops its measurement if the guarded application, session, or owned
project changes. A temporary sleep inhibitor lasts only for the test. It leaves
Ableton open, saves the owned project when it can verify it, and removes its
own audio/MIDI clients when finished. It does not close another project.

Evidence, source and build provenance for the measurement client, and live
`soak-status.json` are under
`~/.local/state/waydaw/reliability-validation-20261118/`.
No representative third-party plugin collection or external audio interface
was available for this test. Those combinations and physical round-trip latency
remain separate acceptance work when that production equipment is available.
