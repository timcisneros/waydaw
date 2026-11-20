"""Inject signal and clock faults without a host audio server or scheduling changes."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include <stdio.h>
#include <stdlib.h>
#include "audio-observation-json.h"
int main(int argc, char **argv) {
    (void)argc;
    int fault = atoi(argv[1]);
    struct audio_meter m;
    struct audio_observation s;
    audio_meter_init(&m, 48000);
    if (fault == 4) {
        audio_meter_clock(&m, UINT32_MAX - 1023, 2048, 1);
        audio_meter_clock(&m, 1024, 2048, 42666668);
        audio_meter_clock(&m, 5000, 2048, 85333335);
        audio_meter_clock(&m, 9000, 2048, 150000000);
    }
    for (unsigned i = 0; i < 3 * 48000; ++i) {
        if (fault != 4 && i % 1024 == 0)
            audio_meter_clock(&m, i, 1024, (uint64_t)i * 1000000000 / 48000);
        double t = (double)i / 48000;
        if (fault == 2 && i >= 48000) t += .001;
        double a = .05 * sin(6.283185307179586 * 440 * t)
                 + (fault == 6 ? 0 : .025 * sin(6.283185307179586 * 997 * t));
        if (fault == 1 && i >= 70000 && i < 72048) a = 0;
        if (fault == 3 && i == 70000) a = NAN;
        if (fault == 7 && i >= 47990 && i < 48020) a = 0;
        double b = fault == 5 ? 0 : a;
        if (audio_meter_sample(&m, a, b, i % 1024, &s)) {
            if (fault == 4 && s.graph_position != (UINT64_C(1) << 32) + 9000)
                return 1;
            audio_observation_write(stdout, &s, 3, 0);
        }
    }
}
'''


class AudioMeterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "driver.c"
        cls.binary = Path(cls.temp.name) / "driver"
        source.write_text(DRIVER)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                        "-I", str(ROOT / "validation"), str(source), "-lm", "-o", str(cls.binary)],
                       check=True, capture_output=True)

    def observe(self, fault):
        result = subprocess.run([str(self.binary), str(fault)], check=True,
                                capture_output=True, text=True)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_continuous_two_tone_signal(self):
        for row in self.observe(0):
            self.assertGreater(row["tone_energy_fraction"], .9999995)
            self.assertAlmostEqual(row["rms"], .03952847075, places=9)
            self.assertLessEqual(row["max_zero_run"], 1)
            self.assertLess(row["phase_step_radians"], 1e-8)
            self.assertIsNone(row["first_clock_discontinuity"])

    def test_missing_buffer(self):
        row = self.observe(1)[1]
        self.assertGreaterEqual(row["max_zero_run"], 2048)
        self.assertLess(row["tone_energy_fraction"], .99)
        self.assertEqual(row["longest_zero_run_start"], {
            "graph_frame": 70000, "callback_monotonic_ns": 1450666666,
        })

    def test_phase_jump_at_window_boundary(self):
        rows = self.observe(2)
        self.assertGreater(rows[1]["tone_energy_fraction"], .9999995)
        self.assertGreater(rows[1]["phase_step_radians"], 1)
        self.assertLess(rows[2]["phase_step_radians"], 1e-8)

    def test_nonfinite_sample(self):
        self.assertEqual(self.observe(3)[1]["nonfinite_samples"], 1)

    def test_frame_clock_wrap_is_valid_but_skip_is_detected(self):
        row, after, _ = self.observe(4)
        self.assertEqual(row["clock_discontinuities"], 2)
        self.assertEqual(row["first_clock_discontinuity"], {
            "graph_frame": 5000, "expected_graph_frame": 3072, "frames": 2048,
            "monotonic_ns": 85333335, "previous_monotonic_ns": 42666668,
        })
        self.assertEqual(row["longest_callback_interval_end"], {
            "graph_frame": 9000, "expected_graph_frame": 7048, "frames": 2048,
            "monotonic_ns": 150000000, "previous_monotonic_ns": 85333335,
        })
        self.assertAlmostEqual(row["longest_callback_interval_us"], 64666.665)
        self.assertEqual(after["clock_discontinuities"], 0)
        self.assertIsNone(after["first_clock_discontinuity"])
        self.assertIsNone(after["longest_callback_interval_end"])

    def test_zero_run_retains_its_start_across_measurement_windows(self):
        before, after, _ = self.observe(7)
        self.assertEqual(before["max_zero_run"], 10)
        self.assertEqual(after["max_zero_run"], 30)
        expected = {"graph_frame": 47990, "callback_monotonic_ns": 981333333}
        self.assertEqual(before["longest_zero_run_start"], expected)
        self.assertEqual(after["longest_zero_run_start"], expected)

    def test_channel_loss(self):
        self.assertGreater(self.observe(5)[1]["channel_difference_rms"], .03)

    def test_absent_second_carrier_does_not_create_phase_faults(self):
        for row in self.observe(6):
            self.assertGreater(row["tone_energy_fraction"], .9999995)
            self.assertLess(row["phase_step_radians"], 1e-8)


if __name__ == "__main__":
    unittest.main()
