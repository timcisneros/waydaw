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
#include "audio-meter.h"
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
    }
    for (unsigned i = 0; i < 3 * 48000; ++i) {
        double t = (double)i / 48000;
        if (fault == 2 && i >= 48000) t += .001;
        double a = .05 * sin(6.283185307179586 * 440 * t)
                 + (fault == 6 ? 0 : .025 * sin(6.283185307179586 * 997 * t));
        if (fault == 1 && i >= 70000 && i < 72048) a = 0;
        if (fault == 3 && i == 70000) a = NAN;
        double b = fault == 5 ? 0 : a;
        if (audio_meter_sample(&m, a, b, &s))
            printf("{\"second\":%u,\"fraction\":%.12f,\"rms\":%.12f,\"zero\":%u,\"nonfinite\":%u,\"clock_gaps\":%u,\"phase_step\":%.12f,\"difference\":%.12f,\"graph_position\":%llu}\n",
                s.second, s.tone_fraction, s.rms, s.max_zero_run, s.nonfinite,
                s.clock_discontinuities, s.phase_step_radians, s.channel_difference_rms,
                (unsigned long long)s.graph_position);
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
            self.assertGreater(row["fraction"], .9999995)
            self.assertAlmostEqual(row["rms"], .03952847075, places=9)
            self.assertLessEqual(row["zero"], 1)
            self.assertLess(row["phase_step"], 1e-8)

    def test_missing_buffer(self):
        row = self.observe(1)[1]
        self.assertGreaterEqual(row["zero"], 2048)
        self.assertLess(row["fraction"], .99)

    def test_phase_jump_at_window_boundary(self):
        rows = self.observe(2)
        self.assertGreater(rows[1]["fraction"], .9999995)
        self.assertGreater(rows[1]["phase_step"], 1)
        self.assertLess(rows[2]["phase_step"], 1e-8)

    def test_nonfinite_sample(self):
        self.assertEqual(self.observe(3)[1]["nonfinite"], 1)

    def test_frame_clock_wrap_is_valid_but_skip_is_detected(self):
        row = self.observe(4)[0]
        self.assertEqual(row["clock_gaps"], 1)
        self.assertEqual(row["graph_position"], 2**32 + 5000)

    def test_channel_loss(self):
        self.assertGreater(self.observe(5)[1]["difference"], .03)

    def test_absent_second_carrier_does_not_create_phase_faults(self):
        for row in self.observe(6):
            self.assertGreater(row["fraction"], .9999995)
            self.assertLess(row["phase_step"], 1e-8)


if __name__ == "__main__":
    unittest.main()
