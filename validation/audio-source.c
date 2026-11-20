#define _POSIX_C_SOURCE 200809L
#include <jack/jack.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <time.h>
#include "audio-observation-json.h"

/* Explicit test source. Connections and scheduling belong to the caller.
 * The output follows the graph clock, including legitimate32-bit wraparound. */
static jack_client_t *client;
static jack_port_t *outputs[2];
static float *signal_samples;
static bool signal_locked;
static struct audio_meter meter;
static struct audio_observation *records;
static unsigned limit, capacity, completed;
static atomic_uint published, driver_notifications;
static volatile sig_atomic_t stopped;

static uint64_t monotonic_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000 + (uint64_t)ts.tv_nsec;
}

static void halt(int signum) { (void)signum; stopped = 1; }
static int xrun(void *unused)
{
    (void)unused;
    atomic_fetch_add(&driver_notifications, 1);
    return 0;
}

static int process(jack_nframes_t count, void *unused)
{
    (void)unused;
    uint32_t frame = jack_last_frame_time(client);
    audio_meter_clock(&meter, frame, count, monotonic_ns());
    float *left = jack_port_get_buffer(outputs[0], count);
    float *right = jack_port_get_buffer(outputs[1], count);
    unsigned position = (unsigned)(meter.graph_position % meter.rate);
    for (unsigned i = 0; i < count; ++i) {
        left[i] = right[i] = signal_samples[position];
        if (++position == meter.rate) position = 0;
        struct audio_observation observation;
        if (audio_meter_sample(&meter, left[i], right[i], i, &observation) && completed < capacity) {
            records[completed++] = observation;
            atomic_store_explicit(&published, completed, memory_order_release);
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 3 || (argc == 3 && strcmp(argv[2], "--hold"))) {
        fprintf(stderr, "usage: audio-source SECONDS [--hold]\n"); return 2;
    }
    bool hold = argc == 3;
    char *end;
    long seconds = strtol(argv[1], &end, 10);
    if (!argv[1][0] || *end || seconds < 1 || seconds > 21600) return 2;
    limit = (unsigned)seconds;
    capacity = limit + (hold ? 30 : 0);
    records = calloc(capacity, sizeof(*records));
    if (!records) return 3;
    for (unsigned i = 0; i < capacity; ++i) records[i].second = UINT32_MAX;
    bool records_locked = mlock(records, capacity * sizeof(*records)) == 0;
    bool meter_locked = mlock(&meter, sizeof(meter)) == 0;
    jack_status_t status = 0;
    client = jack_client_open("waydaw-audio-source", JackNoStartServer | JackUseExactName, &status);
    if (!client) { fprintf(stderr, "JACK client open failed: %u\n", status); free(records); return 4; }
    int result = 0;
    unsigned rate = jack_get_sample_rate(client);
    if (rate != 48000) { fprintf(stderr, "Expected48000Hz, got%u\n", rate); result = 5; goto close; }
    audio_meter_init(&meter, rate);
    signal_samples = calloc(rate, sizeof(*signal_samples));
    if (!signal_samples) { result = 6; goto close; }
    for (unsigned i = 0; i < rate; ++i)
        signal_samples[i] = (float)(.05 * sin(6.2831853071795864769 * 440 * i / rate)
                                 + .025 * sin(6.2831853071795864769 * 997 * i / rate));
    signal_locked = mlock(signal_samples, rate * sizeof(*signal_samples)) == 0;
    outputs[0] = jack_port_register(client, "source_L", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
    outputs[1] = jack_port_register(client, "source_R", JACK_DEFAULT_AUDIO_TYPE, JackPortIsOutput, 0);
    if (!outputs[0] || !outputs[1]) { result = 6; goto close; }
    jack_set_process_callback(client, process, NULL);
    jack_set_xrun_callback(client, xrun, NULL);
    signal(SIGINT, halt); signal(SIGTERM, halt);
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (jack_activate(client)) { result = 7; goto close; }
    uint64_t started_ns = monotonic_ns(), complete_ns = 0;
    printf("{\"event\":\"started\",\"source_only\":true,\"rate\":%u,\"seconds\":%u,\"measurement_memory_locked\":%s}\n", rate, limit, records_locked && meter_locked && signal_locked ? "true" : "false");
    unsigned consumed = 0;
    while (!stopped) {
        unsigned ready = atomic_load_explicit(&published, memory_order_acquire);
        consumed = audio_observations_drain(stdout, records, consumed, ready, limit,
                                            &driver_notifications);
        uint64_t now = monotonic_ns();
        if (!complete_ns && consumed >= limit) complete_ns = now;
        if (complete_ns && (!hold || now - complete_ns >= UINT64_C(30000000000))) break;
        if (now - started_ns > (limit + UINT64_C(60)) * 1000000000) {
            fprintf(stderr, "Measurement exceeded wall-clock deadline\n");
            result = 8; break;
        }
        struct timespec pause = {0, 100000000};
        nanosleep(&pause, NULL);
    }
    int deactivate = jack_deactivate(client);
    unsigned ready = atomic_load_explicit(&published, memory_order_acquire);
    consumed = audio_observations_drain(stdout, records, consumed, ready, limit, &driver_notifications);
    unsigned final_notifications = atomic_load(&driver_notifications);
    if (deactivate) {
        fprintf(stderr, "JACK deactivation failed: %d\n", deactivate);
        if (!result) result = 9;
    } else if (meter.position && consumed < capacity) {
        audio_partial_observation_write(stdout, &meter, consumed < limit, final_notifications);
    }
    printf("{\"event\":\"finished\",\"seconds_observed\":%u,\"requested_seconds\":%u,\"hold_seconds_observed\":%u,\"driver_notifications_seen_by_reader\":%u,\"interrupted\":%s}\n",
        consumed, limit, consumed > limit ? consumed - limit : 0,
        final_notifications, consumed < limit ? "true" : "false");
    if (!result && stopped && consumed < limit) result = 130;
close:
    jack_client_close(client);
    if (records_locked) munlock(records, capacity * sizeof(*records));
    if (meter_locked) munlock(&meter, sizeof(meter));
    if (signal_locked) munlock(signal_samples, rate * sizeof(*signal_samples));
    free(signal_samples);
    free(records);
    return result;
}
