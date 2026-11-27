"""Keep Tk garbage collection on the thread that owns its interpreter."""

import gc

import pytest


@pytest.fixture(autouse=True)
def collect_tk_cycles():
    # Widget callbacks form cycles with their windows. Collect them before a
    # later test's worker can trigger GC and run Tk destructors off the main thread.
    gc.collect()
    yield
    gc.collect()
