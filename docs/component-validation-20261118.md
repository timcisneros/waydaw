# Component validation — 2026-11-18

This is bounded acceptance evidence from the existing Fedora 44 / KDE Plasma
Wayland machine, using the pinned Proton-exp 11.0 runner, DXVK 2.7.1, authorized
Ableton Live 12.4.16 Suite, Bome MIDI Translator Pro 1.9.2, and WineASIO 1.3.0.
It does not establish a production release or replace the remaining gates in
[production readiness](production-readiness.md).

## MIDI

The physical controller was a Launchpad S. Its initial capture showed seven
pad press/release pairs but no forwarded events through the attempted VirMIDI
sequencer route. Replacing that bus with the existing MIDI Through sequencer
port established this path:

```text
Launchpad S → Bome project → Midi Through Port-0 → guarded Ableton
```

The final simultaneous capture contained seven physical note-on/off pairs and
exactly the same fourteen forwarded events. Channel, pitch, velocity, and event
order matched. All note-ons had matching note-offs; there were no duplicates
in this sample. A hardware device-inquiry response also passed through Bome
byte for byte. The Bome project is a pass-through project with no custom
controller mappings.

The captured seven-note sequence was then replayed into MIDI Through and
recorded by native Live into an arrangement clip. Saving and reopening preserved
all seven pitches, velocity 127, positive durations, and one note per replayed
press. This replay is a separate application recording test; it is not an
additional physical pad performance.

A fresh installed desktop **Start with Bome** launch loaded the configured
project. Wine's changing `WINE ALSA Output #N` name caused Ableton to enable an
extra input; optional guarded route maintenance removed that bypass. A further
deliberately reintroduced duplicate route was removed within 1.6 seconds.
This is route-repair timing, not a measurement of MIDI latency. The helpers
verified the resulting exclusive route against the owned Ableton/Bome processes.

## Audio and Max for Live

The project ran at 48 kHz with a 1024-sample ASIO buffer and the machine's
app-scoped ordinary-scheduling PipeWire JACK configuration. A generated 440 Hz
tone was linked explicitly from a temporary PipeWire source to Live's inputs.
No microphone recording was used.

Native Live recorded a mono 24-bit WAV containing approximately ten seconds of
signal, with peak 0.120 and steady RMS 0.08485. The recording track was muted
with monitoring off during input testing to prevent feedback. Separately, the
enabled bundled Max SignalAnalyzer displayed the signal and its track output
was captured: the measured 440 Hz energy fraction exceeded 0.99999998.

After native save and reopen, the recorded waveforms and Max device persisted.
Exporting the recorded track through Live's Main output produced a stereo,
16-bit, 44.1 kHz WAV with ten seconds of active audio, peak 0.120, RMS 0.08485,
and 440 Hz energy fraction above 0.99999995. The exported arrangement included
additional silence outside that signal region.

An initial test-helper attempt opened the set with an unqualified Linux path,
causing samples to appear offline and an export to be silent. Repeating with
the explicit Windows `Z:\…` path resolved the test setup error. The accepted
export was measured after that corrected reopen.

## Evidence and limits

Implementation commit: `d4bdfbc`. All 135 isolated Python regression tests
passed, including guarded routing, Bome project selection, optional maintenance,
and session recovery. ShellCheck 0.10.0, shell syntax checks, and the KWin
compatibility checks passed. These checks do not exercise physical hardware.

Private machine evidence is under
`~/.local/state/waydaw/component-validation-20261118/`, including
`physical-pad-proof.json`, `native-midi-recording-proof.json`,
`recording-and-max-proof.json`, `reopen-export-proof.json`, and
`automatic-route-repair-proof.json`. The native test project is under
`~/Music/WayDAW Validation/Recorded Max Validation Project/`.
Temporary capture streams and explicit audio links were stopped after testing.

The recovery overlay under `~/Backups/waydaw/20261118-components/` preserves
stopped-session preferences, Bome/configuration files, the acceptance project,
and a source Git bundle. It supplements the stopped full-prefix snapshot from
2026-11-17; it is not a new full-prefix or off-machine backup.

Still unverified: reboot and USB reconnect behavior, a representative production
VST2/VST3 collection and custom Bome mappings, round-trip latency, and at least
four hours of the intended workload with measured dropout/xrun results. No
claim of sustained recording stability follows from these short signal tests.
