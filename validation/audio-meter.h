#ifndef WAYDAW_AUDIO_METER_H
#define WAYDAW_AUDIO_METER_H

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/* One-second measurements. No allocation, locking or I/O in the audio path. */
struct audio_observation {
    unsigned second, max_zero_run, nonfinite, clock_discontinuities;
    uint32_t graph_frame;
    uint64_t monotonic_ns, graph_position;
    double rms, right_rms, tone_fraction, channel_difference_rms;
    double phase_step_radians, longest_callback_interval_us;
};

struct audio_meter {
    unsigned rate, position, seconds, zero_run, max_zero_run, nonfinite, clock_gaps;
    uint32_t prior_frame, prior_count, graph_frame;
    uint64_t prior_ns, monotonic_ns, graph_position;
    bool clock_seen, phase_seen[2];
    double energy, right_energy, difference, c[2], s[2], re[2], im[2];
    double rotation_re[2], rotation_im[2], prior_phase[2], longest_interval_us;
};

static inline void audio_meter_init(struct audio_meter *m, unsigned rate)
{
    memset(m, 0, sizeof(*m));
    m->rate = rate;
    const double tau = 6.2831853071795864769;
    const unsigned frequencies[2] = {440, 997};
    for (unsigned j = 0; j < 2; ++j) {
        m->re[j] = 1;
        m->rotation_re[j] = cos(tau * frequencies[j] / rate);
        m->rotation_im[j] = sin(tau * frequencies[j] / rate);
    }
}

static inline void audio_meter_clock(struct audio_meter *m, uint32_t frame,
                                     uint32_t count, uint64_t ns)
{
    if (m->clock_seen) {
        m->graph_position += (uint32_t)(frame - m->prior_frame);
        if (frame != (uint32_t)(m->prior_frame + m->prior_count)) ++m->clock_gaps;
        double interval = (double)(ns - m->prior_ns) / 1000;
        if (interval > m->longest_interval_us) m->longest_interval_us = interval;
    } else m->graph_position = frame;
    m->clock_seen = true;
    m->prior_frame = m->graph_frame = frame;
    m->prior_count = count;
    m->prior_ns = m->monotonic_ns = ns;
}

static inline bool audio_meter_sample(struct audio_meter *m, double a, double b,
                                      struct audio_observation *out)
{
    if (!isfinite(a) || !isfinite(b)) { ++m->nonfinite; a = b = 0; }
    m->energy += a * a;
    m->right_energy += b * b;
    m->difference += (a - b) * (a - b);
    m->zero_run = fabs(a) < 0.000001 ? m->zero_run + 1 : 0;
    if (m->zero_run > m->max_zero_run) m->max_zero_run = m->zero_run;
    for (unsigned j = 0; j < 2; ++j) {
        m->c[j] += a * m->re[j];
        m->s[j] += a * m->im[j];
        double re = m->re[j] * m->rotation_re[j] - m->im[j] * m->rotation_im[j];
        m->im[j] = m->im[j] * m->rotation_re[j] + m->re[j] * m->rotation_im[j];
        m->re[j] = re;
    }
    if (++m->position < m->rate) return false;
    double explained = 0, phase_step = 0;
    for (unsigned j = 0; j < 2; ++j) {
        double tone_energy = 2 * (m->c[j] * m->c[j] + m->s[j] * m->s[j]) / m->rate;
        explained += tone_energy;
        bool present = tone_energy > m->energy * .000001;
        double phase = atan2(-m->c[j], m->s[j]);
        double step = fabs(remainder(phase - m->prior_phase[j], 6.2831853071795864769));
        if (present && m->phase_seen[j] && step > phase_step) phase_step = step;
        m->phase_seen[j] = present;
        m->prior_phase[j] = phase;
        m->c[j] = m->s[j] = m->im[j] = 0;
        m->re[j] = 1;
    }
    *out = (struct audio_observation){
        .second = ++m->seconds, .max_zero_run = m->max_zero_run,
        .nonfinite = m->nonfinite, .clock_discontinuities = m->clock_gaps,
        .graph_frame = m->graph_frame, .monotonic_ns = m->monotonic_ns,
        .graph_position = m->graph_position,
        .rms = sqrt(m->energy / m->rate), .right_rms = sqrt(m->right_energy / m->rate),
        .tone_fraction = m->energy > 0 ? explained / m->energy : 0,
        .channel_difference_rms = sqrt(m->difference / m->rate),
        .phase_step_radians = phase_step,
        .longest_callback_interval_us = m->longest_interval_us
    };
    m->position = m->max_zero_run = m->nonfinite = m->clock_gaps = 0;
    m->energy = m->right_energy = m->difference = m->longest_interval_us = 0;
    return true;
}
#endif
