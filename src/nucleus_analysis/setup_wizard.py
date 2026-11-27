"""First-run guided engine setup; every installation operation stays off Tk."""

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .desktop_launcher import launch
from .managed_setup import SetupCancelled, probe_nvidia, setup_environment
from .preferences import load_preferences, save_preferences


class SetupWizard:
    def __init__(self, root, base, preference_file, *, installer=setup_environment, launch_app=launch):
        self.root, self.base, self.preference_file = root, Path(base), Path(preference_file)
        self.installer, self.launch_app = installer, launch_app
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.ready_python = None
        self.driver = None
        self.log_path = None
        self.closing = False
        self.mode = tk.StringVar(value="cpu")
        preferences = load_preferences(preference_file)
        self.model = tk.StringVar(value=preferences.get("analysis", {}).get("sam2_model", "tiny"))
        if self.model.get() not in ("tiny", "small"):
            self.model.set("tiny")
        self.status = tk.StringVar(value="Checking your computer…")
        self.driver_status = tk.StringVar(value="Checking the NVIDIA driver…")
        self.log_status = tk.StringVar(value="")
        self.stages = [tk.StringVar(value="○ " + text) for text in (
            "Prepare a private analysis environment", "Install PyTorch", "Install Meta SAM 2.1",
            "Download and verify model weights", "Test the model on this computer")]
        root.title("PNC Counter — first-time analysis setup")
        root.geometry("710x700")
        root.minsize(650, 650)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Set up nucleus analysis", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="This one-time setup installs the analysis engine and model. Your choices are saved\n"
                  "for later launches. Your other Python installations are kept separate.", wraplength=650).pack(anchor="w", pady=10)
        processing = ttk.LabelFrame(frame, text="1. Processing", padding=10)
        processing.pack(fill="x")
        self.cpu_choice = ttk.Radiobutton(processing, text="CPU — works without an NVIDIA GPU", variable=self.mode, value="cpu")
        self.cpu_choice.pack(anchor="w")
        self.gpu_choice = ttk.Radiobutton(processing, text="NVIDIA GPU — faster; requires a compatible driver", variable=self.mode,
                                          value="cuda", state="disabled")
        self.gpu_choice.pack(anchor="w", pady=4)
        ttk.Label(processing, textvariable=self.driver_status, wraplength=620).pack(anchor="w", pady=4)
        driver_buttons = ttk.Frame(processing)
        driver_buttons.pack(anchor="w")
        self.detect_button = ttk.Button(driver_buttons, text="Recheck hardware", command=self.detect)
        self.detect_button.pack(side="left")
        ttk.Button(driver_buttons, text="NVIDIA driver downloads", command=lambda: webbrowser.open(
            "https://www.nvidia.com/en-us/drivers/")).pack(side="left", padx=6)
        models = ttk.LabelFrame(frame, text="2. Model", padding=10)
        models.pack(fill="x", pady=10)
        self.model_choice = ttk.Combobox(models, textvariable=self.model, values=("tiny", "small"), state="readonly", width=12)
        self.model_choice.pack(side="left")
        ttk.Label(models, text="SAM 2.1 Tiny: 156 MB · Small: 184 MB\nModel choice can affect nucleus boundaries.").pack(side="left", padx=12)
        ttk.Label(frame, text="An internet connection is needed. CPU packages are hundreds of MB; GPU packages\n"
                  "can be several GB. This may take several minutes. Analysis works offline afterward.",
                  wraplength=650).pack(anchor="w", pady=4)
        for variable in self.stages:
            ttk.Label(frame, textvariable=variable).pack(anchor="w", pady=2)
        self.progress = ttk.Progressbar(frame, maximum=5)
        self.progress.pack(fill="x", pady=(8, 4))
        self.activity = ttk.Progressbar(frame, mode="determinate")
        self.activity.pack(fill="x")
        ttk.Label(frame, textvariable=self.status, wraplength=650).pack(anchor="w", pady=8)
        self.details_frame = ttk.Frame(frame)
        self.details = tk.Text(self.details_frame, height=6, wrap="word", state="disabled")
        self.details.pack(fill="both", expand=True)
        ttk.Label(self.details_frame, textvariable=self.log_status, wraplength=630).pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))
        self.details_button = ttk.Button(buttons, text="Show details", command=self.toggle_details)
        self.details_button.pack(side="left")
        self.runtime_help = ttk.Button(buttons, text="Windows runtime help", command=lambda: webbrowser.open(
            "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist"))
        self.skip_button = ttk.Button(buttons, text="Set up later", command=self.skip)
        self.skip_button.pack(side="left", padx=6)
        self.start_button = ttk.Button(buttons, text="Install and check", command=self.start, state="disabled")
        self.start_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, text="Cancel setup", command=self.request_cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=6)
        root.after(100, self.poll)
        self.detect()

    def running(self):
        return bool(self.worker and self.worker.is_alive())

    def detect(self):
        if self.running():
            return
        self.detect_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.driver_status.set("Checking the NVIDIA driver…")

        def work():
            self.events.put(("driver", probe_nvidia()))
        threading.Thread(target=work, daemon=True).start()

    def set_busy(self, active):
        for widget in (self.cpu_choice, self.gpu_choice, self.model_choice, self.detect_button, self.skip_button):
            state = "disabled" if active else "readonly" if widget is self.model_choice else "normal"
            if widget is self.gpu_choice and not (self.driver or {}).get("cuda_ready"):
                state = "disabled"
            widget.configure(state=state)
        self.start_button.configure(state="disabled" if active else "normal")
        self.cancel_button.configure(state="normal" if active else "disabled")
        self.activity.stop()
        self.activity.configure(mode="indeterminate" if active else "determinate", value=0)
        if active:
            self.activity.start(15)

    def start(self):
        if self.running():
            return
        if self.ready_python:
            self.open_app(self.ready_python)
            return
        if self.mode.get() == "cuda" and not (self.driver or {}).get("cuda_ready"):
            self.status.set("Update the NVIDIA driver and Recheck hardware, or choose CPU processing.")
            return
        self.cancel.clear()
        self.set_busy(True)
        mode, model = self.mode.get(), self.model.get()
        self.status.set("Starting setup…")

        def work():
            try:
                python = self.installer(self.base, self.preference_file, mode, model,
                                        lambda *event: self.events.put(event), self.cancel)
                self.events.put(("ready", python))
            except SetupCancelled:
                self.events.put(("cancelled", None))
            except Exception as exc:
                self.events.put(("failed", str(exc)))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def toggle_details(self):
        if self.details_frame.winfo_manager():
            self.details_frame.pack_forget()
            self.details_button.configure(text="Show details")
            self.root.geometry("710x700")
        else:
            self.details_frame.pack(fill="both", expand=True)
            self.details_button.configure(text="Hide details")
            self.root.geometry("710x850")

    def request_cancel(self):
        self.cancel.set()
        self.status.set("Stopping setup… Your previous working setup will be preserved.")

    def poll(self):
        self.root.after(100, self.poll)
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "driver":
                self.driver = payload
                self.driver_status.set(payload["message"])
                self.mode.set("cuda" if payload["cuda_ready"] else "cpu")
                self.set_busy(False)
            elif kind == "stage":
                completed, text = payload
                self.progress.configure(value=completed)
                self.status.set(text)
                for i, variable in enumerate(self.stages):
                    old = variable.get()[2:]
                    variable.set(("✓ " if i < completed else "→ " if i == completed else "○ ") + old)
            elif kind == "download":
                self.status.set(payload)
            elif kind == "detail":
                self.details.configure(state="normal")
                self.details.insert("end", payload + "\n")
                if int(self.details.index("end-1c").split(".")[0]) > 250:
                    self.details.delete("1.0", "50.0")
                self.details.see("end")
                self.details.configure(state="disabled")
            elif kind == "log":
                self.log_path = payload
                self.log_status.set(f"Setup log: {payload}")
            elif kind == "ready":
                self.ready_python = payload
                self.set_busy(False)
                self.start_button.configure(text="Open PNC Counter")
                self.skip_button.configure(state="disabled")
                self.status.set("Setup verified and saved. You can now open PNC Counter.")
            elif kind in ("failed", "cancelled"):
                self.set_busy(False)
                self.start_button.configure(text="Retry setup")
                self.status.set("Setup cancelled. Retry to continue, or Set up later." if kind == "cancelled" else
                                f"Setup could not finish: {payload}\nCheck your connection or choose CPU. Details and a log are available.")
                if kind == "failed" and self.log_path:
                    try:
                        tail = Path(self.log_path).read_text(encoding="utf-8")[-5000:]
                    except OSError:
                        tail = ""
                    if any(text in tail.lower() for text in ("winerror 126", "winerror 127", "dll load failed", "msvcp140")):
                        self.runtime_help.pack(side="left", padx=4)
                        self.status.set("A Windows runtime library could not load. Use Windows runtime help to install/repair\n"
                                        "the Microsoft Visual C++ x64 runtime, then Retry setup. Your IT team may need to help.")
                if self.closing:
                    self.root.destroy()
                    return

    def open_app(self, python):
        self.launch_app(python, preference_file=self.preference_file)
        self.root.destroy()

    def skip(self):
        if self.running():
            return
        preferences = load_preferences(self.preference_file)
        preferences["setup_skipped"] = True
        save_preferences(self.preference_file, preferences)
        self.open_app(self.base / ("python.exe" if sys.platform == "win32" else "bin/python3"))

    def close(self):
        if self.running():
            if messagebox.askyesno("Stop setup?", "Cancel the current setup? You can retry it later.", parent=self.root):
                self.closing = True
                self.request_cancel()
            return
        self.root.destroy()


def main(base, preference_file):
    root = tk.Tk()
    SetupWizard(root, base, preference_file)
    root.mainloop()
