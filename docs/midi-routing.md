# Launchpad S and Bome routing

The validated path uses ALSA sequencer ports:

```text
Launchpad S → Bome MIDI Router/translators → Midi Through Port-0 → Ableton
```

Keep only MIDI Through enabled as a Track input in Ableton's Tempo & MIDI
settings. Disable the physical Launchpad and Bome's `WINE ALSA Output #N`
input there. Receiving Bome output both directly and through MIDI Through
duplicates notes. Bome's Wine port name can change after reopening ports;
the guarded route helper identifies its owning process instead of that suffix.

The Linux MIDI Through sequencer port relays sequencer events. VirMIDI connects
raw MIDI and sequencer clients; sending sequencer events into it does not make
them reappear as sequencer output. Both Windows applications use Wine's ALSA
sequencer path here, so this setup needs neither `snd-virmidi` nor Bome's
Windows BMIDI kernel driver. Audio continues to use PipeWire JACK/WineASIO.

## Load a Bome project automatically

Copy [the pass-through template](../config/bome-launchpad-s.bmtp) to a writable
project directory and open it in Bome. It preserves MIDI messages and has no
custom translators. Add mappings appropriate to your controller workflow.
Keep its output set to `Midi Through Port-0`. Verify those names exist with
`aconnect -l`; changing hardware requires updating the project.

Store one absolute Linux project path in
`${XDG_CONFIG_HOME:-~/.config}/waydaw/bome-project`, for example:

```text
/home/your-user/Documents/WayDAW MIDI/Launchpad S.bmtp
```

`WAYDAW_BOME_PROJECT=/absolute/path/project.bmtp` overrides that file. An empty
environment value disables automatic project loading. A configured missing,
unreadable, relative, or multiline path fails preflight before Wine starts.
The launcher converts the path using the selected prefix's `winepath`, then
uses Bome's `/project` option. Explicit arguments to `bin/bome` take precedence.
GUI initialization and successful argument delivery still require a real MIDI
signal test to establish project processing.

## Keep the route exclusive during a full session

Put `bome` in `${XDG_CONFIG_HOME:-~/.config}/waydaw/midi-route`, or set
`WAYDAW_MIDI_ROUTE=bome`, and start with `./bin/waydaw start --with-bome` or
the desktop entry's **Start with Bome** action. The supervisor checks the route
every two seconds. It waits for the project to open its physical input and
MIDI Through output, connects the bus to the guarded Ableton instance, and
removes physical/direct Bome bypasses into that instance. Connections to other
applications remain untouched. It does not create Bome translators or routes
inside a project.

Missing hardware, a stopped Bome, or an unavailable route leaves Ableton open
for audio work and saving. State changes appear in the session log as
`midi_routing=waiting` or `midi_routing=ready`. Maintenance is disabled by
default, skipped for Ableton-only sessions, and can be disabled explicitly with
`WAYDAW_MIDI_ROUTE=off` (or an empty value). It runs inside the existing
supervisor; there is no additional background service or boot configuration.
Allow startup to finish and check the route before playing or recording.

## Inspect and change routes manually

| Command | Effect |
| --- | --- |
| `bin/midi-route-inspect` | Read-only inventory scoped to the running guarded Ableton application. |
| `bin/bome-validation-check` | Read-only check of the Bome input/output subscriptions and exclusive Ableton input; exits nonzero when incomplete. |
| `bin/bome-validation-route` | Preview the connections and bypass removals. |
| `bin/bome-validation-route --apply` | Apply the preview after verifying process ownership and port identity again. |
| `bin/launchpad-route-temp` | Preview direct Launchpad input, removing the translated path; add `--apply` to change it. |
| `bin/apply-live-routes` | Apply direct Launchpad input. Enable that input in Ableton first when using this mode. |
| `bin/clear-live-routes` | Remove the known physical/bus connections into the guarded Ableton application. |

The helpers discover names and process ownership instead of hard-coded client
numbers or the first Wine process. If multiple matching devices exist, select
their current addresses with `WAYDAW_LAUNCHPAD_PORT` and
`WAYDAW_MIDI_BUS_PORT`. Overrides must still refer to the expected device type.
They refuse a stale, cancelled, foreign-prefix, or unowned session. Hardware
absence is tolerated when clearing routes. Commands never load kernel modules
or start Wine.

A passing ALSA check proves subscriptions and excludes the known bypasses. It
does not prove Bome processed a message, Ableton recorded it, or notes remained
balanced. Compare physical and forwarded note-on/off events, record a MIDI
clip, and repeat after reconnecting the controller and after a reboot.
