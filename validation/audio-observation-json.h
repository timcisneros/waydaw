#ifndef WAYDAW_AUDIO_OBSERVATION_JSON_H
#define WAYDAW_AUDIO_OBSERVATION_JSON_H

#include <inttypes.h>
#include <stdio.h>
#include "audio-meter.h"

static inline void audio_callback_write(FILE *stream, const struct audio_callback_point *point)
{
    if (!point->count) {
        fputs("null", stream);
        return;
    }
    fprintf(stream,
            "{\"graph_frame\":%" PRIu32 ",\"expected_graph_frame\":%" PRIu32
            ",\"frames\":%" PRIu32 ",\"monotonic_ns\":%" PRIu64
            ",\"previous_monotonic_ns\":%" PRIu64 "}",
            point->frame, point->expected_frame, point->count,
            point->monotonic_ns, point->previous_monotonic_ns);
}

/* Only the reader thread writes JSON. Keep the existing window fields stable. */
static inline void audio_observation_write(FILE *stream, const struct audio_observation *s,
                                           unsigned limit, unsigned notifications)
{
    fprintf(stream,
            "{\"second\":%u,\"phase\":\"%s\",\"graph_frame\":%" PRIu32 ",\"monotonic_ns\":%" PRIu64
            ",\"rms\":%.10f,\"right_rms\":%.10f,\"tone_energy_fraction\":%.12f"
            ",\"max_zero_run\":%u,\"nonfinite_samples\":%u,\"clock_discontinuities\":%u"
            ",\"phase_step_radians\":%.10g,\"longest_callback_interval_us\":%.3f"
            ",\"channel_difference_rms\":%.10g,\"driver_notifications_seen_by_reader\":%u"
            ",\"first_clock_discontinuity\":",
            s->second, s->second <= limit ? "measurement" : "hold", s->graph_frame,
            s->monotonic_ns, s->rms, s->right_rms, s->tone_fraction, s->max_zero_run,
            s->nonfinite, s->clock_discontinuities, s->phase_step_radians,
            s->longest_callback_interval_us, s->channel_difference_rms, notifications);
    audio_callback_write(stream, &s->first_clock_jump);
    fputs(",\"longest_callback_interval_end\":", stream);
    audio_callback_write(stream, &s->longest_interval);
    fputs(",\"longest_zero_run_start\":", stream);
    const struct audio_sample_point *start = &s->longest_zero_run_start;
    if (start->known) {
        fprintf(stream, "{\"graph_frame\":%" PRIu32 ",\"callback_monotonic_ns\":%" PRIu64 "}",
                start->frame, start->callback_monotonic_ns);
    } else {
        fputs("null", stream);
    }
    fputs("}\n", stream);
}
#endif
