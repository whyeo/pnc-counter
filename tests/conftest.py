"""Keep Tk garbage collection on the thread that owns its interpreter."""

import gc
import tkinter as tk

import pytest


@pytest.fixture(autouse=True)
def collect_tk_cycles():
    # Widget callbacks form cycles with their windows. Collect them before a
    # later test's worker can trigger GC and run Tk destructors off the main thread.
    gc.collect()
    yield
    gc.collect()


@pytest.fixture(scope="session")
def tk_session():
    # Tk windows share one interpreter, as they do in the real application.
    # Repeatedly unloading/reloading Tk and its native drag/drop extension is
    # unreliable on Windows, even when garbage collection runs on the owner thread.
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_window(tk_session):
    window = tk.Toplevel(tk_session)
    window.withdraw()
    yield window
    if window.winfo_exists():
        window.destroy()
