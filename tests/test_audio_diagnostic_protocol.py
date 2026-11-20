"""Exercise diagnostic completion/hold output without an audio server or RT grants."""
from pathlib import Path
import json
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADER = r'''
#include <stdint.h>
typedef uint32_t jack_nframes_t;
typedef unsigned jack_status_t;
typedef struct { int unused; } jack_client_t;
typedef struct { float samples[48000]; } jack_port_t;
enum { JackNoStartServer = 1, JackUseExactName = 2,
       JackPortIsInput = 1, JackPortIsOutput = 2 };
#define JACK_DEFAULT_AUDIO_TYPE "audio"
jack_client_t *jack_client_open(const char *, unsigned, jack_status_t *, ...);
int jack_client_close(jack_client_t *);
jack_nframes_t jack_get_sample_rate(jack_client_t *);
jack_nframes_t jack_last_frame_time(jack_client_t *);
jack_port_t *jack_port_register(jack_client_t *, const char *, const char *, unsigned long, unsigned long);
void *jack_port_get_buffer(jack_port_t *, jack_nframes_t);
int jack_set_process_callback(jack_client_t *, int (*)(jack_nframes_t, void *), void *);
int jack_set_xrun_callback(jack_client_t *, int (*)(void *), void *);
int jack_activate(jack_client_t *);
int jack_deactivate(jack_client_t *);
'''
FAKE_JACK = r'''
#define _POSIX_C_SOURCE 200809L
#include <jack/jack.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <time.h>
static jack_client_t client;
static jack_port_t ports[3];
static unsigned port_count, frame;
static int (*process_callback)(jack_nframes_t, void *), (*xrun_callback)(void *);
static void *process_arg, *xrun_arg;
static pthread_t worker;
static atomic_bool running;
jack_client_t *jack_client_open(const char *name, unsigned options, jack_status_t *status, ...) {
    (void)name; (void)options; *status = 0; return &client;
}
int jack_client_close(jack_client_t *c) { (void)c; return 0; }
jack_nframes_t jack_get_sample_rate(jack_client_t *c) { (void)c; return 48000; }
jack_nframes_t jack_last_frame_time(jack_client_t *c) { (void)c; return frame; }
jack_port_t *jack_port_register(jack_client_t *c, const char *name, const char *type, unsigned long flags, unsigned long size) {
    (void)c; (void)name; (void)type; (void)flags; (void)size;
    return port_count < 3 ? &ports[port_count++] : 0;
}
void *jack_port_get_buffer(jack_port_t *port, jack_nframes_t count) { (void)count; return port->samples; }
int jack_set_process_callback(jack_client_t *c, int (*callback)(jack_nframes_t, void *), void *arg) {
    (void)c; process_callback = callback; process_arg = arg; return 0;
}
int jack_set_xrun_callback(jack_client_t *c, int (*callback)(void *), void *arg) {
    (void)c; xrun_callback = callback; xrun_arg = arg; return 0;
}
static void *feed(void *unused) {
    (void)unused;
    unsigned cycles = 0;
    while (atomic_load(&running)) {
        process_callback(48000, process_arg);
        frame += 48000;
        /* The first HOLD callback skips a quantum. */
        if (cycles == 0) frame += 48000;
        /* A report after the requested one-second measurement must remain visible. */
        if (++cycles == 2) xrun_callback(xrun_arg);
        struct timespec pause = {0, 1000000};
        nanosleep(&pause, 0);
    }
    return 0;
}
int jack_activate(jack_client_t *c) {
    (void)c; atomic_store(&running, true); return pthread_create(&worker, 0, feed, 0);
}
int jack_deactivate(jack_client_t *c) {
    (void)c; atomic_store(&running, false); return pthread_join(worker, 0);
}
'''


class AudioDiagnosticProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        (directory / "jack").mkdir()
        (directory / "jack/jack.h").write_text(HEADER)
        (directory / "fake-jack.c").write_text(FAKE_JACK)
        cls.binaries = []
        for name in ["audio-source", "audio-monitor"]:
            binary = directory / name
            subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I", str(directory), str(ROOT / "validation" / (name + ".c")),
                            str(directory / "fake-jack.c"), "-pthread", "-lm", "-o", str(binary)],
                           check=True, capture_output=True)
            cls.binaries.append(binary)

    def observe(self, binary, hold):
        process = subprocess.Popen([str(binary), "1", *(["--hold"] if hold else [])],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timer = threading.Timer(1, lambda: process.terminate() if process.poll() is None else None)
        if hold:
            timer.start()
        try:
            stdout, stderr = process.communicate(timeout=5)
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(process.returncode, 0, stderr)
        return [json.loads(line) for line in stdout.splitlines()]

    def test_fixed_measurement_finishes_without_hold_observations(self):
        for binary in self.binaries:
            with self.subTest(binary=binary.name):
                rows = self.observe(binary, hold=False)
                samples = [row for row in rows if "second" in row]
                self.assertEqual([(row["second"], row["phase"]) for row in samples], [(1, "measurement")])
                self.assertEqual(rows[-1]["hold_seconds_observed"], 0)
                self.assertFalse(rows[-1]["interrupted"])

    def test_hold_publishes_continuity_and_reports_after_completion(self):
        for binary in self.binaries:
            with self.subTest(binary=binary.name):
                rows = self.observe(binary, hold=True)
                completion = [i for i, row in enumerate(rows) if row.get("event") == "measurement_complete"]
                self.assertEqual(len(completion), 1)
                self.assertEqual(rows[completion[0]]["seconds_observed"], 1)
                self.assertGreater(rows[completion[0]]["measurement_end_monotonic_ns"], 0)
                self.assertIsNone(rows[completion[0] - 1]["first_clock_discontinuity"])
                held = [row for row in rows[completion[0] + 1:] if row.get("phase") == "hold"]
                self.assertGreater(len(held), 0)
                self.assertLessEqual(len(held), 30)
                self.assertTrue(all(row["second"] > 1 for row in held))
                jump = held[0]["first_clock_discontinuity"]
                self.assertEqual(jump["graph_frame"], 96000)
                self.assertEqual(jump["expected_graph_frame"], 48000)
                self.assertEqual(jump["frames"], 48000)
                self.assertEqual(jump["previous_monotonic_ns"], rows[completion[0]]["measurement_end_monotonic_ns"])
                self.assertEqual(jump["monotonic_ns"], held[0]["monotonic_ns"])
                self.assertGreaterEqual(held[-1]["driver_notifications_seen_by_reader"], 1)
                self.assertEqual(rows[-1]["event"], "finished")
                self.assertEqual(rows[-1]["requested_seconds"], 1)
                self.assertEqual(rows[-1]["hold_seconds_observed"], len(held))
                self.assertGreaterEqual(rows[-1]["driver_notifications_seen_by_reader"], 1)
                self.assertFalse(rows[-1]["interrupted"])


if __name__ == "__main__":
    unittest.main()
