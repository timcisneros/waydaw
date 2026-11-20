"""Seed the clock in a disposable WineASIO 1.3.0 source tree for clock-host.c."""

import argparse
from pathlib import Path


def replace_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError(f"Expected exactly one WineASIO source anchor for {anchor.strip()!r}")
    return source.replace(anchor, replacement)


def seed_clock(path):
    source = path.read_text()
    stock_reset = "    This->host_num_samples.hi = This->host_num_samples.lo = 0;"
    atomic_reset = "    atomic_store_explicit(&This->host_num_samples, 0, memory_order_relaxed);"
    if stock_reset in source:
        reset = stock_reset
        store = """    This->host_num_samples.hi = (ULONG)(seed >> 32);
    This->host_num_samples.lo = (ULONG)seed;"""
    else:
        reset = atomic_reset
        store = "    atomic_store_explicit(&This->host_num_samples, seed, memory_order_relaxed);"

    source = replace_once(source, "#include <stdio.h>", "#include <stdio.h>\n#include <stdlib.h>")
    source = replace_once(source, "    DWORD           time;\n\n    TRACE", """    DWORD           time;
    char            seed_buffer[32];
    unsigned long long seed = 0;

    TRACE""")
    source = replace_once(source, reset, """    if (GetEnvironmentVariableA("WAYDAW_TEST_ASIO_START_POSITION", seed_buffer, sizeof(seed_buffer)))
        seed = strtoull(seed_buffer, NULL, 10);
""" + store)
    source = replace_once(source, "        This->host_time.numSamples.lo = This->host_time.numSamples.hi = 0;",
                          """        This->host_time.numSamples.lo = (ULONG)seed;
        This->host_time.numSamples.hi = (ULONG)(seed >> 32);""")
    path.write_text(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch_asio_source", type=Path, help="path to a disposable copy of asio.c")
    seed_clock(parser.parse_args().scratch_asio_source)
