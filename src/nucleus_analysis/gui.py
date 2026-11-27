"""Simple desktop batch workflow with saved setup and explicit acquisition checks."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import fields, replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .cli import discover_inputs, run_batch
from .config import AnalysisConfig
from .preferences import (
    cached_hardware,
    detect_hardware,
    find_checkpoint,
    load_preferences,
    preferences_path,
    save_preferences,
)
from .workflow import inspect_image, raw_preview, suggest_channels

CHOICES = {"backend": ("sam2", "sam3", "watershed"), "device": ("cpu", "cuda", "mps"),
           "sam2_model": ("tiny", "small", "base_plus", "large"),
           "threshold_mode": ("local", "global"), "quality_filter": ("none", "legacy-svm"),
           "border_policy": ("include", "exclude"), "pnc_mode": ("pixels", "spots")}
OPTIONAL_FLOATS = {"min_nucleus_area_um2", "max_nucleus_area_um2", "pixel_size_x_um", "pixel_size_y_um"}


class CounterApp:
    def __init__(self, root, *, preference_file=None, initialize=True):
        self.root = root
        self.preference_file = Path(preference_file) if preference_file else preferences_path()
        self.preferences = load_preferences(self.preference_file)
        try:
            self.config = AnalysisConfig(**self.preferences.get("analysis", {}))
        except (ValueError, TypeError):
            self.config = AnalysisConfig()
        self.paths, self.editors, self.controls = [], [], []
        self.item_by_path, self.path_by_item, self.output_by_item, self.metadata = {}, {}, {}, {}
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.background_threads = []
        self.preparing = self.setup_busy = self.download_busy = self.closing = False
        self.hardware = cached_hardware(self.preferences)
        self.preview_image = None
        self.preview_token = 0
        self.total = self.completed = self.failed = 0
        self.started_at = None
        self.current_stage = None
        self.last_clock_update = 0
        self.values = {f.name: tk.StringVar(value="" if getattr(self.config, f.name) is None
                                           else str(getattr(self.config, f.name)))
                       for f in fields(AnalysisConfig) if f.name != "checkpoint"}
        self.device_choice = tk.StringVar(value=self.preferences.get("device_choice", "auto"))
        self.manual_channels = tk.BooleanVar(value=self.preferences.get("manual_channels", False))
        self.checkpoint = tk.StringVar(value=find_checkpoint(self.config.sam2_model, self.config.checkpoint,
                                                             self.model_roots()))
        self.output = tk.StringVar(value=self.preferences.get("output", str(Path("results").resolve())))
        self.status = tk.StringVar(value="Add images or drop a folder to begin.")
        self.file_status = tk.StringVar(value="Drop ND2 / multichannel TIFF images or a folder here")
        self.hardware_status, self.protocol_status = tk.StringVar(), tk.StringVar()
        root.title("Nucleus Analysis — PNC Counter")
        root.geometry("1180x800")
        root.minsize(920, 650)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew")
        for label, command in [("Add images", self.select_files), ("Add folder", self.select_folder),
                               ("Remove selected", self.remove_selected), ("Open saved analysis", self.open_saved)]:
            self._button(toolbar, label, command).pack(side="left", padx=(0, 6))
        self._button(toolbar, "Advanced settings", self.advanced_settings).pack(side="right")
        self.drop_zone = ttk.Label(frame, textvariable=self.file_status, anchor="center", padding=14, relief="groove")
        self.drop_zone.grid(row=1, column=0, sticky="ew", pady=10)
        details = ttk.Frame(frame)
        details.grid(row=2, column=0, sticky="ew")
        ttk.Label(details, textvariable=self.protocol_status).pack(side="left")
        ttk.Label(details, textvariable=self.hardware_status).pack(side="right")
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, sticky="ew", pady=10)
        for label, command in [("Analyze images", self.start), ("Check channels", self.check_channels),
                               ("Review / correct selected", self.review_selected), ("Open results folder", self.open_results)]:
            self._button(actions, label, command).pack(side="left", padx=(0, 6))
        self.cancel_button = ttk.Button(actions, text="Stop after this image", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="right")
        panes = ttk.PanedWindow(frame, orient="horizontal")
        panes.grid(row=4, column=0, sticky="nsew")
        listing = ttk.Frame(panes)
        self.table = ttk.Treeview(listing, columns=("file", "status", "positive", "total", "percent"),
                                  show="headings", selectmode="extended")
        for name, heading, width in [("file", "Filename", 190), ("status", "Status", 125),
                                      ("positive", "PNC+", 55), ("total", "Nuclei", 55), ("percent", "Percent", 70)]:
            self.table.heading(name, text=heading)
            self.table.column(name, width=width, stretch=name in ("file", "status"))
        scrollbar = ttk.Scrollbar(listing, command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.show_preview)
        self.table.bind("<Double-1>", lambda _e: self.review_selected())
        panes.add(listing, weight=3)
        preview_frame = ttk.Frame(panes)
        self.preview = ttk.Label(preview_frame, text="Select an image to preview its channels", anchor="center")
        self.preview.pack(fill="both", expand=True)
        self.preview_caption = tk.StringVar(value="Preview contrast is adjusted for display only.")
        ttk.Label(preview_frame, textvariable=self.preview_caption, wraplength=430).pack(fill="x", pady=6)
        panes.add(preview_frame, weight=2)
        output_row = ttk.Frame(frame)
        output_row.grid(row=5, column=0, sticky="ew", pady=10)
        ttk.Label(output_row, text="Save results to: ").pack(side="left")
        ttk.Label(output_row, textvariable=self.output).pack(side="left", fill="x", expand=True)
        self._button(output_row, "Change…", self.select_output).pack(side="right")
        progress_frame = ttk.Frame(frame)
        progress_frame.grid(row=6, column=0, sticky="ew")
        progress_frame.columnconfigure(1, weight=1)
        ttk.Label(progress_frame, text="Images finished", width=18).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(progress_frame, maximum=1)
        self.progress.grid(row=0, column=1, sticky="ew")
        ttk.Label(progress_frame, text="Current step", width=18).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.stage_bar = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.stage_bar.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.set_activity(False)
        ttk.Label(frame, textvariable=self.status, wraplength=1120).grid(row=8, column=0, sticky="w", pady=8)
        self.drop_enabled = False
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD

            TkinterDnD.require(root)
            for widget in (self.drop_zone, self.table, self.preview):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.drop_files)
            self.drop_enabled = True
        except (ImportError, RuntimeError, tk.TclError):
            self.file_status.set("Use Add images / Add folder (drag-and-drop unavailable in this Tk installation)")
        self.refresh_protocol()
        self.refresh_hardware_label()
        root.after(100, self.poll)
        if initialize and not self.hardware:
            root.after(50, self.redetect_hardware)

    def model_roots(self):
        return (self.preference_file.parent / "models", Path.cwd() / "models",
                Path(__file__).resolve().parents[2] / "models")

    def _button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append((widget, "normal"))
        return widget

    def _entry(self, parent, variable, **kwargs):
        return ttk.Entry(parent, textvariable=variable, **kwargs)

    def busy(self):
        return self.preparing or bool(self.worker and self.worker.is_alive())

    def start_background(self, target):
        # Keep the window alive until workers have released their references to
        # its Tk variables and images. Tk objects must be destroyed on Tk's thread.
        self.background_threads = [t for t in self.background_threads if t.is_alive()]
        thread = threading.Thread(target=target, daemon=True)
        self.background_threads.append(thread)
        thread.start()
        return thread

    def persist(self):
        self.preferences.update(output=self.output.get(), device_choice=self.device_choice.get(),
                                manual_channels=self.manual_channels.get())
        try:
            save_preferences(self.preference_file, self.preferences)
        except OSError as exc:
            self.status.set(f"Preferences could not be saved: {exc}")

    def refresh_protocol(self):
        self.protocol_status.set(f"Protocol: {self.values['backend'].get().upper()} "
                                 f"{self.values['sam2_model'].get()} · PNC {self.values['pnc_mode'].get()}")

    def refresh_hardware_label(self):
        text = "Detecting hardware (one-time setup)…" if self.setup_busy else "Hardware setup pending"
        if self.hardware and not self.setup_busy:
            text = f"{self.hardware['name']} · saved setup"
            if not self.hardware.get("sam2_installed"):
                text += " · SAM 2 runtime needs installation"
        self.hardware_status.set(text)

    def redetect_hardware(self):
        if self.setup_busy or self.busy():
            return
        self.setup_busy = True
        self.set_activity(True)
        self.refresh_hardware_label()

        def work():
            try:
                self.events.put(("hardware", detect_hardware()))
            except Exception as exc:
                self.events.put(("setup_error", str(exc)))
        self.start_background(work)

    def select_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Microscopy images", "*.nd2 *.ND2 *.tif *.tiff *.TIF *.TIFF")])
        if paths:
            self.add_paths(paths)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.add_paths([folder])

    def drop_files(self, event):
        if self.busy():
            return "refuse_drop"
        self.add_paths(self.root.tk.splitlist(event.data))
        return "copy"

    def add_paths(self, paths):
        if self.busy():
            return
        folders = []
        for value in paths:
            path = Path(value).resolve()
            if path.is_dir():
                folders.append(path)
            elif path.is_file() and path.suffix.lower() in (".nd2", ".tif", ".tiff"):
                self.add_image(path)
        if folders:
            self.preparing = True
            self.status.set("Finding images in the selected folders…")

            def scan():
                for folder in folders:
                    try:
                        for path in discover_inputs(folder, recursive=True):
                            if not any((p / "analysis.json").is_file() for p in path.parents):
                                self.events.put(("input", path))
                    except (ValueError, OSError) as exc:
                        self.events.put(("input_error", str(exc)))
                self.events.put(("scan_done", None))
            self.start_background(scan)

    def add_image(self, path):
        path = Path(path).resolve()
        if path in self.item_by_path:
            return self.item_by_path[path]
        item = self.table.insert("", "end", values=(path.name, "Ready", "", "", ""))
        self.paths.append(path)
        self.item_by_path[path], self.path_by_item[item] = item, path
        self.file_status.set(f"{len(self.paths)} images added · drop more images or folders here")
        self.status.set(f"{len(self.paths)} images ready. Select an image to preview it, then Analyze images.")
        if len(self.paths) == 1:
            self.table.selection_set(item)
        return item

    def remove_selected(self):
        if self.busy():
            return
        for item in self.table.selection():
            path = self.path_by_item.pop(item, None)
            if path is not None:
                self.item_by_path.pop(path, None)
                self.paths.remove(path)
            self.output_by_item.pop(item, None)
            self.table.delete(item)
        self.file_status.set(f"{len(self.paths)} images added · drop images or folders here")
        self.show_preview()

    def select_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output.set(folder)
            self.persist()

    def select_checkpoint(self):
        path = filedialog.askopenfilename(filetypes=[("Model checkpoint", "*.pt *.pth")])
        if path:
            self.checkpoint.set(path)

    def get_config(self):
        defaults = AnalysisConfig()
        updates = {}
        for name, var in self.values.items():
            text = var.get().strip()
            updates[name] = (float(text) if text else None) if name in OPTIONAL_FLOATS else type(getattr(defaults, name))(text)
        updates["checkpoint"] = self.checkpoint.get() or None
        updates["device"] = ((self.hardware or {}).get("device", "cpu") if self.device_choice.get() == "auto"
                             else self.device_choice.get())
        return replace(self.config, **updates)

    def advanced_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced settings")
        dialog.geometry("680x730")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Settings are remembered. Automatic acceleration keeps the selected model and analysis rules.",
                  wraplength=620, padding=12).pack(fill="x")
        performance = ttk.Frame(dialog, padding=8)
        performance.pack(fill="x")
        ttk.Label(performance, text="Processing device").pack(side="left")
        ttk.Combobox(performance, textvariable=self.device_choice, values=("auto", "cpu", "cuda", "mps"),
                     state="readonly", width=10).pack(side="left", padx=8)
        ttk.Button(performance, text="Redetect hardware", command=self.redetect_hardware).pack(side="left")
        ttk.Button(performance, text="Set up / repair SAM", command=self.setup_sam).pack(side="left", padx=6)
        ttk.Label(dialog, textvariable=self.hardware_status, padding=8).pack(fill="x")
        ttk.Label(dialog, textvariable=self.status, wraplength=620, padding=8).pack(fill="x")
        tabs = ttk.Notebook(dialog)
        tabs.pack(fill="both", expand=True, padx=8)
        groups = {
            "Nuclei": ["backend", "sam2_model", "min_nucleus_area", "max_nucleus_area", "quality_filter",
                       "overlap_threshold", "border_policy", "border_margin", "min_nucleus_area_um2", "max_nucleus_area_um2"],
            "PNC": ["threshold_mode", "image_threshold", "positive_threshold", "neighborhood_size", "pnc_mode",
                    "min_spot_count", "spot_min_area", "spot_max_area", "spot_min_distance", "spot_background_sigma", "review_positive_margin"],
            "Acquisition": ["dapi_channel", "pnc_channel", "time_index", "position_index", "pixel_size_x_um", "pixel_size_y_um"],
            "Model": ["points_per_side", "points_per_batch", "score_threshold", "stability_threshold",
                      "watershed_min_distance", "watershed_sigma", "sam3_prompt"],
        }
        original = {name: var.get() for name, var in self.values.items()}
        original_checkpoint, original_device = self.checkpoint.get(), self.device_choice.get()
        original_manual = self.manual_channels.get()
        original_config = self.config
        for title, names in groups.items():
            page = ttk.Frame(tabs, padding=10)
            tabs.add(page, text=title)
            page.columnconfigure(1, weight=1)
            for row, name in enumerate(names):
                label = name.replace("_", " ").capitalize()
                if name in OPTIONAL_FLOATS:
                    label += " (blank = metadata / pixels)"
                ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", pady=5)
                if name in CHOICES:
                    widget = ttk.Combobox(page, textvariable=self.values[name], values=CHOICES[name], state="readonly")
                else:
                    widget = ttk.Entry(page, textvariable=self.values[name])
                widget.grid(row=row, column=1, sticky="ew", padx=8)
        model_page = tabs.winfo_children()[-1]
        acquisition_page = tabs.winfo_children()[2]
        ttk.Checkbutton(acquisition_page, text="Use these channel / time / position indices for every image",
                        variable=self.manual_channels).grid(row=7, columnspan=2, sticky="w", pady=10)
        ttk.Label(acquisition_page, text="Leave unchecked to detect metadata and remember choices using Check channels.",
                  wraplength=580).grid(row=8, columnspan=2, sticky="w")
        ttk.Label(model_page, text="Checkpoint").grid(row=8, column=0, sticky="w")
        ttk.Entry(model_page, textvariable=self.checkpoint).grid(row=8, column=1, sticky="ew")
        ttk.Button(model_page, text="Choose checkpoint", command=self.select_checkpoint).grid(row=9, column=0, pady=8)
        ttk.Button(model_page, text="Download SAM 2.1 model", command=self.download_model).grid(row=9, column=1)
        ttk.Label(model_page, text="Use Set up / repair SAM above to install the analysis engine in the Windows installer edition.\n"
                  "Changing the model may change counts. Leave the device on Auto to use your GPU.",
                  wraplength=580).grid(row=10, columnspan=2, sticky="w")
        buttons = ttk.Frame(dialog, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Import protocol", command=self.import_settings).pack(side="left")
        ttk.Button(buttons, text="Export protocol", command=self.export_settings).pack(side="left", padx=4)

        def dismiss():
            self.config = original_config
            for name, text in original.items():
                self.values[name].set(text)
            self.checkpoint.set(original_checkpoint)
            self.device_choice.set(original_device)
            self.manual_channels.set(original_manual)
            self.refresh_protocol()
            dialog.destroy()

        def apply():
            try:
                model = self.values["sam2_model"].get()
                if model != original_config.sam2_model and self.checkpoint.get() == original_checkpoint:
                    self.checkpoint.set(find_checkpoint(model, roots=self.model_roots()))
                self.config = self.get_config()
                self.preferences["analysis"] = self.config.to_dict()
                self.persist()
                self.refresh_protocol()
                dialog.destroy()
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Settings", str(exc), parent=dialog)
        ttk.Button(buttons, text="Save settings", command=apply).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=dismiss).pack(side="right", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", dismiss)

    def import_settings(self):
        path = filedialog.askopenfilename(filetypes=[("Settings JSON", "*.json")])
        if path:
            try:
                self.config = AnalysisConfig.load(path)
                for name, var in self.values.items():
                    value = getattr(self.config, name)
                    var.set("" if value is None else str(value))
                self.checkpoint.set(find_checkpoint(self.config.sam2_model, self.config.checkpoint, self.model_roots()))
                self.device_choice.set(self.config.device)
                self.refresh_protocol()
            except (ValueError, OSError, TypeError) as exc:
                messagebox.showerror("Settings", str(exc))

    def export_settings(self):
        try:
            config = self.get_config()
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Settings JSON", "*.json")])
            if path:
                config.save(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Settings", str(exc))

    def check_channels(self):
        selection = self.table.selection()
        if selection and selection[0] in self.path_by_item and not self.busy():
            self.prepare([self.path_by_item[selection[0]]], analyze=False)

    def channel_dialog(self, path, metadata):
        mapping, _ = suggest_channels(metadata)
        mapping.update(self.preferences.get("channel_mappings", {}).get(metadata["signature"], {}))
        dialog = tk.Toplevel(self.root)
        dialog.title("Check acquisition channels")
        dialog.transient(self.root)
        dialog.grab_set()
        names = [f"{i + 1}: {name}" for i, name in enumerate(metadata["channels"])]
        ttk.Label(dialog, text=f"{path.name}\nChoose the nuclei stain and PNC marker. This choice will be remembered\n"
                  "for images with the same channel names and acquisition layout.", padding=12).grid(row=0, columnspan=2)
        variables = {}
        for row, (key, label) in enumerate((("dapi_channel", "Nuclei / DAPI"), ("pnc_channel", "PNC marker")), 1):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=12, sticky="w")
            variables[key] = tk.StringVar(value=names[min(mapping[key], len(names) - 1)])
            ttk.Combobox(dialog, textvariable=variables[key], values=names, state="readonly", width=35).grid(row=row, column=1, pady=6)
        indices = {}
        for row, (axis, key, label) in enumerate((("T", "time_index", "Time point"), ("P", "position_index", "Position")), 3):
            count = metadata["sizes"].get(axis, 1)
            indices[key] = tk.IntVar(value=mapping.get(key, 0) + 1)
            if count > 1:
                ttk.Label(dialog, text=f"{label} (1–{count}; analyze one)").grid(row=row, column=0, padx=12)
                ttk.Spinbox(dialog, from_=1, to=count, textvariable=indices[key], width=8).grid(row=row, column=1, sticky="w")
        image_label = ttk.Label(dialog, text="Loading channel preview…")
        image_label.grid(row=5, columnspan=2, padx=10, pady=10)
        scale = metadata.get("pixel_size_um")
        ttk.Label(dialog, text=(f"Metadata calibration: {scale['x']:g} × {scale['y']:g} µm / pixel" if scale
                               else "No physical calibration found. Area rules use pixels unless specified in Advanced settings."),
                  wraplength=500).grid(row=6, columnspan=2, padx=10)
        result = []

        def selected():
            return {**{key: names.index(var.get()) for key, var in variables.items()},
                    **{key: var.get() - 1 for key, var in indices.items()}}

        def preview():
            try:
                config = replace(self.get_config(), **selected())
            except (ValueError, tk.TclError):
                return
            self.preview_token += 1
            token = self.preview_token

            def load():
                try:
                    image = raw_preview(path, config, (500, 280))
                except Exception as exc:
                    image = str(exc)
                self.events.put(("dialog_preview", (token, image_label, image)))
            self.start_background(load)

        def apply():
            try:
                chosen = selected()
                replace(self.get_config(), **chosen)
                for axis, key in (("T", "time_index"), ("P", "position_index")):
                    if chosen[key] >= metadata["sizes"].get(axis, 1):
                        raise ValueError(f"{axis} selection is out of range")
                result.append(chosen)
                dialog.destroy()
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Channels", str(exc), parent=dialog)
        buttons = ttk.Frame(dialog)
        buttons.grid(row=7, columnspan=2, pady=12)
        ttk.Button(buttons, text="Refresh preview", command=preview).pack(side="left", padx=6)
        ttk.Button(buttons, text="Use these channels", command=apply).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=6)
        preview()
        self.root.wait_window(dialog)
        return result[0] if result else None

    def prepare(self, paths, *, analyze):
        self.preparing = True
        self.set_controls(False)
        self.status.set("Checking acquisition metadata and saved channel mappings…")

        def work():
            metadata, errors = {}, []
            for path in paths:
                try:
                    metadata[path] = inspect_image(path)
                except Exception as exc:
                    errors.append((path, str(exc)))
            self.events.put(("prepared", (paths, metadata, errors, analyze)))
        self.start_background(work)

    def finish_prepare(self, payload):
        paths, metadata, errors, analyze = payload
        if self.closing:
            self.preparing = False
            return
        self.metadata.update(metadata)
        if errors:
            for path, error in errors:
                self.table.set(self.item_by_path[path], "status", "Cannot read image")
            messagebox.showerror("Acquisition", "\n".join(f"{p.name}: {e}" for p, e in errors))
            self.preparing = False
            self.set_controls(True)
            return
        mappings = self.preferences.setdefault("channel_mappings", {})
        configs = {}
        try:
            base = self.get_config()
            for path in paths:
                meta = metadata[path]
                key = meta["signature"]
                if analyze and self.manual_channels.get():
                    if max(base.dapi_channel, base.pnc_channel) >= len(meta["channels"]):
                        raise ValueError(f"{path.name}: manual channel selection is out of range")
                    for axis, index in (("T", base.time_index), ("P", base.position_index)):
                        if index >= meta["sizes"].get(axis, 1):
                            raise ValueError(f"{path.name}: manual {axis} selection is out of range")
                    configs[path] = base
                    continue
                if key in mappings and not isinstance(mappings[key], dict):
                    del mappings[key]
                if not analyze or key not in mappings:
                    proposed, confident = suggest_channels(meta)
                    if analyze and confident and all(meta["sizes"].get(a, 1) == 1 for a in "TP"):
                        mappings[key] = {**proposed, "time_index": 0, "position_index": 0}
                    else:
                        chosen = self.channel_dialog(path, meta)
                        if chosen is None:
                            self.status.set("Channel check cancelled. Your images remain in the list.")
                            return
                        mappings[key] = chosen
                configs[path] = replace(base, **mappings[key])
            self.persist()
            if analyze:
                self.launch_batch(paths, base, configs)
            else:
                self.show_preview()
                self.status.set("Channel choice saved for this acquisition layout.")
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Settings", str(exc))
        finally:
            self.preparing = False
            if not self.worker or not self.worker.is_alive():
                self.set_controls(True)

    def start(self):
        if self.busy():
            return
        if any(editor.window.winfo_exists() for editor in self.editors):
            messagebox.showinfo("Review in progress", "Close review windows before processing another batch.")
            return
        if not self.paths:
            messagebox.showinfo("Add images", "Add or drop images or a folder first.")
            return
        if self.setup_busy or not self.hardware:
            self.status.set("Hardware setup is required before analysis. Please wait for detection to finish.")
            if not self.setup_busy:
                self.redetect_hardware()
            return
        try:
            config = self.get_config()
            if config.backend == "sam2" and not self.hardware.get("sam2_installed"):
                self.setup_sam()
                return
            if config.backend.startswith("sam") and (not config.checkpoint or not Path(config.checkpoint).is_file()):
                messagebox.showinfo("Model setup", "Choose or download the selected model under Advanced settings → Model.")
                self.advanced_settings()
                return
            self.config = config
            self.preferences["analysis"] = config.to_dict()
            self.persist()
            self.prepare(list(self.paths), analyze=True)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Settings", str(exc))

    def set_controls(self, enabled):
        for widget, state in self.controls:
            if widget.winfo_exists():
                widget.configure(state=state if enabled else "disabled")

    def setup_sam(self):
        from .desktop_launcher import launch
        from .managed_setup import runtime_base

        if self.busy() or self.download_busy:
            return
        if any(editor.window.winfo_exists() for editor in self.editors):
            messagebox.showinfo("Review in progress", "Save and close review windows before opening setup.")
            return
        base = runtime_base()
        if base is None:
            messagebox.showinfo("Guided setup", "Guided setup is included in the Windows installer edition.\n"
                                "For a Python/wheel installation, use the SAM installation instructions in README.md.")
            return
        self.preferences["analysis"] = self.get_config().to_dict()
        self.persist()
        launch(base / "python.exe", setup=True, preference_file=self.preference_file)
        self.root.destroy()

    def set_activity(self, active):
        self.stage_bar.stop()
        self.stage_bar.configure(mode="indeterminate" if active else "determinate", value=0)
        if active:
            self.stage_bar.start(15)

    def launch_batch(self, paths, config, configs):
        output = Path(self.output.get())
        self.cancel.clear()
        self.total, self.completed, self.failed = len(paths), 0, 0
        self.started_at = time.monotonic()
        self.current_stage = None
        self.progress.configure(maximum=self.total, value=0)
        self.set_activity(True)
        self.set_controls(False)
        self.cancel_button.configure(state="normal")
        for path in paths:
            item = self.item_by_path[path]
            self.table.item(item, values=(path.name, "Queued", "", "", ""))
            self.output_by_item.pop(item, None)
            self.metadata.get(path, {}).pop("error", None)

        def work():
            try:
                run_batch(paths, config, output, cache=output / ".cache", cancelled=self.cancel.is_set,
                          progress=lambda *args: self.events.put(("result", args)),
                          stage_progress=lambda *args: self.events.put(("stage", args)),
                          config_for_path=lambda path: configs[path])
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        self.worker = self.start_background(work)

    def progress_text(self, path, stage):
        elapsed = max(0, time.monotonic() - self.started_at) if self.started_at else 0
        estimate = (f" · about {round(elapsed / self.completed * (self.total - self.completed))}s remaining"
                    if self.completed and self.completed < self.total else "")
        return f"{self.completed} of {self.total} finished · {path.name}: {stage} · {round(elapsed)}s elapsed{estimate}"

    def update_result(self, path, stats, destination, error):
        item = self.item_by_path.get(Path(path).resolve())
        if item is None:
            return
        self.completed += 1
        self.progress.configure(value=self.completed)
        if error:
            self.failed += 1
            self.table.item(item, values=(path.name, "Error — select for details", "", "", ""))
            self.status.set(f"{path.name}: {error}")
            self.metadata.setdefault(path, {})["error"] = str(error)
        else:
            self.set_counts(item, stats, "Done")
            self.output_by_item[item] = destination
            self.status.set(self.progress_text(path, "Done"))
        if item in self.table.selection():
            self.show_preview()

    def set_counts(self, item, stats, state):
        percent = f"{stats['percentage']:.2f}%" if stats["percentage"] is not None else "N/A"
        name = self.table.set(item, "file")
        self.table.item(item, values=(name, state, stats["n_positive"], stats["n_total"], percent))

    def poll(self):
        # Schedule before draining: channel confirmation runs a nested Tk loop.
        # Its background previews must keep receiving events during wait_window.
        self.root.after(100, self.poll)
        self.drain_events()
        if self.current_stage and time.monotonic() - self.last_clock_update > 1:
            self.status.set(self.progress_text(*self.current_stage))
            self.last_clock_update = time.monotonic()

    def drain_events(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "hardware":
                self.hardware = payload
                self.preferences["hardware"] = payload
                self.setup_busy = False
                self.set_activity(False)
                self.persist()
                self.refresh_hardware_label()
                self.status.set("Setup saved. Future launches reuse it; Redetect hardware is in Advanced settings.")
            elif kind == "setup_error":
                self.setup_busy = False
                self.set_activity(False)
                self.refresh_hardware_label()
                self.status.set(f"Setup failed: {payload}. Use Redetect hardware to retry.")
            elif kind == "input":
                self.add_image(payload)
            elif kind == "input_error":
                self.status.set(payload)
            elif kind == "scan_done":
                self.preparing = False
                self.status.set(f"{len(self.paths)} images ready. Select an image to preview it, then Analyze images.")
            elif kind == "prepared":
                self.finish_prepare(payload)
            elif kind == "stage":
                path, stage = payload
                self.current_stage = (path, stage)
                self.table.set(self.item_by_path[path.resolve()], "status", stage)
                self.status.set(self.progress_text(path, stage))
            elif kind == "result":
                self.update_result(*payload)
            elif kind == "error":
                messagebox.showerror("Processing", payload)
            elif kind == "done":
                self.current_stage = None
                self.set_controls(True)
                self.cancel_button.configure(state="disabled")
                self.set_activity(False)
                for item in self.table.get_children():
                    if self.table.set(item, "status") == "Queued":
                        self.table.set(item, "status", "Not run")
                verb = "Stopped" if self.cancel.is_set() else "Finished"
                elapsed = round(time.monotonic() - self.started_at) if self.started_at else 0
                self.status.set(f"{verb}: {self.completed} of {self.total} images finished · "
                                f"{self.failed} errors · {elapsed}s elapsed. Select a result to review nuclei.")
            elif kind in ("preview", "dialog_preview"):
                token, target, image = payload
                if token != self.preview_token or not target.winfo_exists():
                    continue
                if isinstance(image, str):
                    target.configure(image="", text=image)
                else:
                    photo = ImageTk.PhotoImage(image)
                    target.configure(image=photo, text="")
                    target.image = photo
            elif kind == "download":
                self.status.set(payload)
            elif kind == "download_done":
                self.download_busy = False
                self.checkpoint.set(payload)
                self.status.set("Model downloaded and verified. Save settings to use it.")
            elif kind == "download_error":
                self.download_busy = False
                self.status.set(f"Model download failed: {payload}")

    def show_preview(self, _event=None):
        self.preview_token += 1
        token = self.preview_token
        selection = self.table.selection()
        if not selection:
            self.preview.configure(image="", text="Select an image to preview its channels")
            return
        item = selection[0]
        path, directory = self.path_by_item.get(item), self.output_by_item.get(item)
        self.preview.configure(image="", text="Loading preview…")
        size = (max(300, self.preview.winfo_width() - 16), max(250, self.preview.winfo_height() - 16))
        try:
            config = self.get_config()
            meta = self.metadata.get(path, {})
            mapping = self.preferences.get("channel_mappings", {}).get(meta.get("signature"))
            if mapping:
                config = replace(config, **mapping)
            if self.manual_channels.get():
                config = self.get_config()
        except ValueError as exc:
            self.preview.configure(text=str(exc))
            return
        if meta.get("error"):
            self.preview_caption.set(f"Analysis error: {meta['error']}")
        else:
            self.preview_caption.set("Completed overlay. Double-click the row to review nuclei." if directory else
                                     "Raw image, first Z plane. Display contrast only; use Check channels to confirm the marker.")

        def load():
            try:
                if directory:
                    with Image.open(directory / "visualization.png") as source:
                        source.thumbnail(size)
                        image = source.copy()
                else:
                    image = raw_preview(path, config, size) if path else "No source image available"
            except Exception as exc:
                image = f"Preview unavailable: {exc}"
            self.events.put(("preview", (token, self.preview, image)))
        self.start_background(load)

    def download_model(self):
        from .setup_model import download_checkpoint

        if self.download_busy:
            return
        model = self.values["sam2_model"].get()
        if model not in ("tiny", "small"):
            messagebox.showinfo("Checkpoint", "Choose Tiny or Small for verified download, or browse to an existing checkpoint.")
            return
        target = self.preference_file.parent / "models" / f"sam2.1_hiera_{model}.pt"
        self.download_busy = True
        self.status.set("Preparing model download…")

        def work():
            try:
                download_checkpoint(model, target, lambda text: self.events.put(("download", text)))
                self.events.put(("download_done", str(target)))
            except Exception as exc:
                self.events.put(("download_error", str(exc)))
        self.start_background(work)

    def open_results(self):
        path = Path(self.output.get()).resolve()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def open_saved(self):
        path = filedialog.askopenfilename(title="Open analysis.json from an original or reviewed result",
                                          filetypes=[("Analysis JSON", "analysis.json"), ("JSON", "*.json")])
        if path:
            try:
                directory = Path(path).resolve().parent
                metadata = json.loads(Path(path).read_text(encoding="utf-8"))
                item = self.table.insert("", "end", values=(directory.name, "Done", "", "", ""))
                self.set_counts(item, metadata["summary"], "Done")
                self.output_by_item[item] = directory
                self.table.selection_set(item)
                self.show_preview()
                self.review_selected()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("Open analysis", str(exc))

    def review_selected(self):
        if self.busy():
            return
        selection = self.table.selection()
        if not selection or selection[0] not in self.output_by_item:
            messagebox.showinfo("Review nuclei", "Select a completed result first, or open a saved analysis.")
            return
        item = selection[0]
        directory = self.output_by_item[item]
        for editor in self.editors:
            if editor.window.winfo_exists() and editor.directory == directory:
                editor.window.lift()
                return
        try:
            from .editor import ReviewEditor

            def saved(path, stats):
                self.output_by_item[item] = path
                self.set_counts(item, stats, "Reviewed")
                self.status.set(f"Reviewed counts saved to {path}")
                self.show_preview()
            self.editors.append(ReviewEditor(self.root, directory, on_saved=saved))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Review nuclei", str(exc))

    def close(self):
        for editor in self.editors:
            if editor.window.winfo_exists():
                editor.close()
                if editor.window.winfo_exists():
                    return
        if self.busy() or any(t.is_alive() for t in self.background_threads):
            self.closing = True
            self.cancel.set()
            self.status.set("Finishing the current task before closing…")
            self.root.after(500, self.close)
            return
        self.root.destroy()


def main():
    from .desktop_launcher import main as launch_main

    launch_main([])


if __name__ == "__main__":
    main()
