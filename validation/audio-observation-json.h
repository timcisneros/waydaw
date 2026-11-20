#ifndef WAYDAW_AUDIO_OBSERVATION_JSON_H
#define WAYDAW_AUDIO_OBSERVATION_JSON_H

#include <inttypes.h>
#include <stdatomic.h>
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

static inline void audio_fault_details_write(FILE *stream, const struct audio_callback_point *jump,
                                            const struct audio_callback_point *longest,
                                            const struct audio_sample_point *silence)
{
    fputs(",\"first_clock_discontinuity\":", stream);
    audio_callback_write(stream, jump);
    fputs(",\"longest_callback_interval_end\":", stream);
    audio_callback_write(stream, longest);
    fputs(",\"longest_zero_run_start\":", stream);
    if (silence->known) {
        fprintf(stream, "{\"graph_frame\":%" PRIu32 ",\"callback_monotonic_ns\":%" PRIu64 "}",
                silence->frame, silence->callback_monotonic_ns);
    } else {
        fputs("null", stream);
    }
    fputs("}\n", stream);
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
            ",\"channel_difference_rms\":%.10g,\"driver_notifications_seen_by_reader\":%u",
            s->second, s->second <= limit ? "measurement" : "hold", s->graph_frame,
            s->monotonic_ns, s->rms, s->right_rms, s->tone_fraction, s->max_zero_run,
            s->nonfinite, s->clock_discontinuities, s->phase_step_radians,
            s->longest_callback_interval_us, s->channel_difference_rms, notifications);
    audio_fault_details_write(stream, &s->first_clock_jump, &s->longest_interval, &s->longest_zero_run_start);
}

static inline unsigned audio_observations_drain(FILE *stream, const struct audio_observation *records,
                                               unsigned consumed, unsigned ready, unsigned limit,
                                               const atomic_uint *notifications)
{
    while (consumed < ready) {
        const struct audio_observation *s = &records[consumed++];
        audio_observation_write(stream, s, limit, atomic_load(notifications));
        if (consumed == limit) {
            fprintf(stream, "{\"event\":\"measurement_complete\",\"seconds_observed\":%u"
                    ",\"measurement_end_monotonic_ns\":%" PRIu64 "}\n", limit, s->monotonic_ns);
        }
    }
    return consumed;
}

/* Read the in-progress window only after JACK has stopped the process callback. */
static inline void audio_partial_observation_write(FILE *stream, const struct audio_meter *m,
                                                   bool measuring, unsigned notifications)
{
    fprintf(stream, "{\"event\":\"partial_observation\",\"window_phase\":\"%s\",\"samples\":%u,\"rate\":%u"
            ",\"graph_frame\":%" PRIu32 ",\"monotonic_ns\":%" PRIu64
            ",\"max_zero_run\":%u,\"nonfinite_samples\":%u,\"clock_discontinuities\":%u"
            ",\"driver_notifications_seen_by_reader\":%u",
            measuring ? "measurement" : "hold", m->position, m->rate, m->graph_frame,
            m->monotonic_ns, m->max_zero_run, m->nonfinite, m->clock_gaps, notifications);
    audio_fault_details_write(stream, &m->first_clock_jump, &m->longest_interval, &m->longest_zero_run_start);
}
#endif
