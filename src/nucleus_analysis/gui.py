"""Tk desktop workflow; one worker thread, bounded memory, no web server."""

import json
import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .cli import discover_inputs, run_batch
from .config import AnalysisConfig


class CounterApp:
    def __init__(self, root):
        self.root = root
        self.config = AnalysisConfig()
        self.paths = []
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.output_by_item = {}
        self.preview_image = None
        self.editors = []
        root.title("Nucleus Analysis — PNC Counter")
        root.geometry("1100x760")
        root.minsize(850, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        self.controls = []
        files = ttk.Frame(frame)
        files.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._button(files, "Select files", self.select_files).pack(side="left")
        self._button(files, "Select folder", self.select_folder).pack(side="left", padx=6)
        self._button(files, "Open saved analysis", self.open_saved).pack(side="left")
        self.file_status = tk.StringVar(value="Select ND2 or multichannel TIFF images")
        ttk.Label(files, textvariable=self.file_status).pack(side="left", padx=12)
        self.output = tk.StringVar(value=str(Path("results").resolve()))
        ttk.Label(frame, text="Output folder").grid(row=1, column=0, sticky="w")
        self._entry(frame, self.output).grid(row=1, column=1, sticky="ew", padx=8)
        self._button(frame, "Browse", self.select_output).grid(row=1, column=2)
        settings = ttk.LabelFrame(frame, text="Analysis settings", padding=8)
        settings.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        self.values = {}
        fields = [
            ("backend", "Segmentation", ("sam2", "sam3", "watershed")),
            ("device", "Device", ("cpu", "cuda", "mps")),
            ("sam2_model", "SAM 2.1 model", ("tiny", "small", "base_plus", "large")),
            ("threshold_mode", "PNC threshold mode", ("local", "global")),
            ("image_threshold", "Image threshold (0–100)", None),
            ("positive_threshold", "Positive pixels / nucleus", None),
            ("min_nucleus_area", "Minimum nucleus area (px)", None),
            ("max_nucleus_area", "Maximum nucleus area (px)", None),
            ("dapi_channel", "DAPI channel (zero-based)", None),
            ("pnc_channel", "PNC channel (zero-based)", None),
            ("quality_filter", "Mask quality filter", ("none", "legacy-svm")),
            ("sam3_prompt", "SAM 3 text prompt", None),
        ]
        for i, (name, label, options) in enumerate(fields):
            row, col = divmod(i, 3)
            col *= 2
            ttk.Label(settings, text=label).grid(row=row, column=col, sticky="w", padx=4, pady=4)
            var = tk.StringVar(value=str(getattr(self.config, name)))
            self.values[name] = var
            if options:
                widget = ttk.Combobox(settings, textvariable=var, values=options,
                                      state="readonly", width=14)
                self.controls.append((widget, "readonly"))
            else:
                widget = self._entry(settings, var, width=14)
            widget.grid(row=row, column=col + 1, sticky="ew", padx=4, pady=4)
            settings.columnconfigure(col + 1, weight=1)
        default_checkpoint = Path("models/sam2.1_hiera_tiny.pt")
        self.checkpoint = tk.StringVar(value=str(default_checkpoint.resolve())
                                       if default_checkpoint.is_file() else "")
        ttk.Label(settings, text="Model checkpoint").grid(row=4, column=0, sticky="w", padx=4)
        self._entry(settings, self.checkpoint).grid(row=4, column=1, columnspan=4, sticky="ew", padx=4)
        self._button(settings, "Browse", self.select_checkpoint).grid(row=4, column=5)
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._button(actions, "Import settings", self.import_settings).pack(side="left")
        self._button(actions, "Export settings", self.export_settings).pack(side="left", padx=6)
        self._button(actions, "Process all", self.start).pack(side="left", padx=20)
        self._button(actions, "Review / correct selected", self.review_selected).pack(side="left", padx=4)
        self.cancel_button = ttk.Button(actions, text="Cancel after current image", command=self.cancel.set,
                                        state="disabled")
        self.cancel_button.pack(side="left")
        self.status = tk.StringVar(value="Ready. SAM requires a local checkpoint; see README for setup.")
        panes = ttk.PanedWindow(frame, orient="horizontal")
        panes.grid(row=4, column=0, columnspan=3, sticky="nsew")
        self.table = ttk.Treeview(panes, columns=("file", "positive", "total", "percent"),
                                  show="headings", selectmode="browse")
        for name, heading, width in [("file", "Filename", 180), ("positive", "PNC+", 65),
                                      ("total", "Nuclei", 65), ("percent", "Percent", 75)]:
            self.table.heading(name, text=heading)
            self.table.column(name, width=width, stretch=name == "file")
        self.table.bind("<<TreeviewSelect>>", self.show_preview)
        self.table.bind("<Double-1>", lambda _e: self.review_selected())
        panes.add(self.table, weight=1)
        self.preview = ttk.Label(panes, text="Select a completed image to inspect its visualization", anchor="center")
        panes.add(self.preview, weight=2)
        ttk.Label(frame, textvariable=self.status, wraplength=1000).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        root.after(100, self.poll)

    def _button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append((widget, "normal"))
        return widget

    def _entry(self, parent, variable, **kwargs):
        widget = ttk.Entry(parent, textvariable=variable, **kwargs)
        self.controls.append((widget, "normal"))
        return widget

    def select_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Microscopy images", "*.nd2 *.ND2 *.tif *.tiff")])
        if paths:
            self.paths = [Path(p) for p in paths]
            self.file_status.set(f"{len(self.paths)} images selected")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            try:
                self.paths = discover_inputs(Path(folder))
                self.file_status.set(f"{len(self.paths)} images selected")
            except ValueError as exc:
                messagebox.showerror("Input folder", str(exc))

    def select_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output.set(folder)

    def select_checkpoint(self):
        path = filedialog.askopenfilename(filetypes=[("Model checkpoint", "*.pt *.pth"), ("All files", "*")])
        if path:
            self.checkpoint.set(path)

    def get_config(self):
        updates = {}
        for name, var in self.values.items():
            old = getattr(self.config, name)
            updates[name] = type(old)(var.get())
        updates["checkpoint"] = self.checkpoint.get() or None
        return replace(self.config, **updates)

    def import_settings(self):
        path = filedialog.askopenfilename(filetypes=[("Settings JSON", "*.json")])
        if path:
            try:
                self.config = AnalysisConfig.load(path)
                for name, var in self.values.items():
                    var.set(str(getattr(self.config, name)))
                self.checkpoint.set(self.config.checkpoint or "")
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

    def start(self):
        if any(editor.window.winfo_exists() for editor in self.editors):
            messagebox.showinfo("Review in progress", "Close review windows before processing another batch.")
            return
        if not self.paths:
            messagebox.showerror("Input", "Select files or an input folder first")
            return
        try:
            config = self.get_config()
            output = Path(self.output.get())
            if config.backend.startswith("sam") and (not config.checkpoint or not Path(config.checkpoint).is_file()):
                raise ValueError("Select a local SAM checkpoint first; see README for download instructions")
        except ValueError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self.table.delete(*self.table.get_children())
        self.output_by_item.clear()
        self.cancel.clear()
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set("Processing; model inference can take a few minutes on CPU…")

        def worker():
            try:
                run_batch(self.paths, config, output, cache=output / ".cache",
                          cancelled=self.cancel.is_set,
                          progress=lambda *args: self.events.put(("result", args)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def poll(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "result":
                path, stats, destination, error = payload
                if error:
                    self.table.insert("", "end", values=(path.name, "ERROR", "", ""))
                    self.status.set(f"{path.name}: {error}")
                else:
                    percent = f"{stats['percentage']:.2f}%" if stats["percentage"] is not None else "N/A"
                    item = self.table.insert("", "end", values=(path.name, stats["n_positive"], stats["n_total"], percent))
                    self.output_by_item[item] = destination
                    self.status.set(f"Completed {path.name}; outputs saved to {destination}")
            elif kind == "error":
                messagebox.showerror("Processing", payload)
            elif kind == "done":
                for widget, state in self.controls:
                    widget.configure(state=state)
                self.cancel_button.configure(state="disabled")
                self.status.set("Cancelled after current image." if self.cancel.is_set()
                                else f"Finished. Results and errors are saved in {self.output.get()}")
        self.root.after(100, self.poll)

    def show_preview(self, _event=None):
        selection = self.table.selection()
        if selection and selection[0] in self.output_by_item:
            with Image.open(self.output_by_item[selection[0]] / "visualization.png") as image:
                image.thumbnail((max(400, self.preview.winfo_width()), max(300, self.preview.winfo_height())))
                self.preview_image = ImageTk.PhotoImage(image.copy())
            self.preview.configure(image=self.preview_image, text="")

    def open_saved(self):
        path = filedialog.askopenfilename(title="Open analysis.json from an original or reviewed result",
                                          filetypes=[("Analysis JSON", "analysis.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            directory = Path(path).resolve().parent
            metadata = json.loads(Path(path).read_text(encoding="utf-8"))
            stats = metadata["summary"]
            percent = f"{stats['percentage']:.2f}%" if stats["percentage"] is not None else "N/A"
            item = self.table.insert("", "end", values=(directory.name, stats["n_positive"], stats["n_total"], percent))
            self.output_by_item[item] = directory
            self.table.selection_set(item)
            self.show_preview()
            self.review_selected()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Open analysis", str(exc))

    def review_selected(self):
        if self.worker and self.worker.is_alive():
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
                values = list(self.table.item(item, "values"))
                percent = f"{stats['percentage']:.2f}%" if stats["percentage"] is not None else "N/A"
                self.table.item(item, values=(values[0], stats["n_positive"], stats["n_total"], percent))
                self.status.set(f"Reviewed counts saved to {path}; original batch files are preserved.")
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
        if self.worker and self.worker.is_alive():
            self.cancel.set()
            self.status.set("Finishing the current image before closing…")
            self.root.after(500, self.close)
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    CounterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
