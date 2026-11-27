"""Lightweight Tk nucleus review window with polygon and freehand corrections."""

import copy
import json
import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image, ImageTk
from scipy import ndimage as ndi

from .imaging import scale_uint8
from .review import ReviewSession

PNC_METHODS = {"Background-aware (preview)": "adaptive", "Legacy pixel count": "pixels", "Legacy spot count": "spots"}


def render_review(session, selected=(), channel="DAPI", show_masks=True):
    """Render masks in original pixel coordinates, including flagged/rejected objects."""
    _, details = session.counts()
    dapi = session.projections.dapi_max
    if channel == "DAPI + PNC":
        base = np.stack([scale_uint8(session.projections.pnc_max), dapi // 3, dapi], axis=-1)
    else:
        gray = {"DAPI": dapi, "PNC": scale_uint8(session.projections.pnc_max),
                "PNC threshold": session._positive_pixels.astype(np.uint8) * 255}[channel]
        base = np.repeat(gray[..., None], 3, axis=-1)
    if not show_masks:
        return Image.fromarray(base)
    selected = set(selected)
    order = sorted(session.masks, key=lambda i: (i in selected, not details[i]["rejected"], i))
    flat = base.reshape(-1, 3)
    for identifier in order:
        mask = session.masks[identifier]
        color = ((180, 180, 180) if details[identifier]["rejected"] else
                 (100, 160, 255) if details[identifier]["positive"] else (255, 153, 179))
        edge_color = (110, 255, 110) if identifier in selected else (255, 220, 20) if mask.flagged else color
        idx = mask.pixels
        flat[idx] = (flat[idx] * 0.65 + np.array(color) * 0.35).astype(np.uint8)
        yy, xx = np.unravel_index(idx, session.shape)
        y0, x0 = yy.min(), xx.min()
        local = np.zeros((yy.max() - y0 + 1, xx.max() - x0 + 1), dtype=bool)
        local[yy - y0, xx - x0] = True
        edge = local & ~ndi.binary_erosion(local, structure=np.ones((3, 3)), border_value=0)
        ey, ex = np.nonzero(edge)
        base[ey + y0, ex + x0] = edge_color
    return Image.fromarray(base)


class ReviewEditor:
    def __init__(self, parent, directory, on_saved=None, on_protocol=None):
        self.session = ReviewSession.open(directory)
        self.directory = Path(directory).resolve()
        self.on_saved = on_saved
        self.on_protocol = on_protocol
        self._pnc_token = 0
        self._pnc_after = None
        self._pending_pnc = None
        self._pnc_worker = None
        self._syncing_pnc = False
        self.selected = set()
        self.points = []
        self.tool_target = None
        self.busy = False
        self.events = queue.Queue()
        self.photo = None
        self.window = tk.Toplevel(parent)
        self.window.title(f"Review nuclei - {self.directory.name}")
        self.window.geometry("1180x820")
        self.window.minsize(950, 650)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(2, weight=1)
        self.buttons = []
        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.tool = tk.StringVar(value="Select")
        self.channel = tk.StringVar(value="DAPI + PNC")
        self.show_masks = tk.BooleanVar(value=True)
        self.show_ids = tk.BooleanVar(value=True)
        for name in ("Select", "Add", "Redraw", "Split"):
            button = ttk.Radiobutton(toolbar, text=name, variable=self.tool, value=name,
                                     command=self.change_tool)
            button.pack(side="left", padx=3)
            self.buttons.append(button)
        self.button(toolbar, "Finish outline (Enter)", self.finish_outline).pack(side="left", padx=10)
        self.button(toolbar, "Cancel outline (Esc)", self.cancel_outline).pack(side="left")
        channels = ttk.Combobox(toolbar, values=("DAPI", "PNC", "DAPI + PNC", "PNC threshold"),
                                 textvariable=self.channel, state="readonly", width=16)
        channels.pack(side="right", padx=6)
        channels.bind("<<ComboboxSelected>>", lambda _e: self.render())
        self.stats = tk.StringVar()
        ttk.Label(self.window, textvariable=self.stats, padding=(10, 3), font=("TkDefaultFont", 11, "bold")).grid(
            row=1, column=0, columnspan=2, sticky="w")
        image_frame = ttk.Frame(self.window)
        image_frame.grid(row=2, column=0, sticky="nsew")
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(image_frame, background="#171b24", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        horizontal = ttk.Scrollbar(image_frame, orient="horizontal", command=self.canvas.xview)
        vertical = ttk.Scrollbar(image_frame, orient="vertical", command=self.canvas.yview)
        horizontal.grid(row=1, column=0, sticky="ew")
        vertical.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<Button-3>", self.remove_vertex)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", lambda e: self.zoom(1.25, e))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(0.8, e))
        self.canvas.bind("<ButtonPress-2>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        sidebar_shell = ttk.Frame(self.window)
        sidebar_shell.grid(row=2, column=1, sticky="ns")
        sidebar_shell.rowconfigure(0, weight=1)
        side_canvas = tk.Canvas(sidebar_shell, width=265, highlightthickness=0)
        side_canvas.grid(row=0, column=0, sticky="ns")
        side_scroll = ttk.Scrollbar(sidebar_shell, orient="vertical", command=side_canvas.yview)
        side_scroll.grid(row=0, column=1, sticky="ns")
        side_canvas.configure(yscrollcommand=side_scroll.set)
        sidebar = ttk.Frame(side_canvas, padding=8)
        side_window = side_canvas.create_window(0, 0, window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", lambda _e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))
        side_canvas.bind("<Configure>", lambda e: side_canvas.itemconfigure(side_window, width=e.width))
        tuning = ttk.LabelFrame(sidebar, text="PNC sensitivity", padding=6)
        tuning.pack(fill="x", pady=(0, 8))
        self.pnc_method = tk.StringVar(value=next(k for k, v in PNC_METHODS.items() if v == self.session.config.pnc_mode))
        method = ttk.Combobox(tuning, textvariable=self.pnc_method, values=tuple(PNC_METHODS), state="readonly", width=27)
        self.pnc_method_box = method
        method.pack(fill="x")
        method.bind("<<ComboboxSelected>>", self.schedule_pnc_preview)
        self.pnc_sensitivity = tk.DoubleVar(value=self.session.config.pnc_sensitivity)
        self.pnc_slider = ttk.Scale(tuning, from_=0, to=100, variable=self.pnc_sensitivity,
                                    command=self.schedule_pnc_preview)
        self.pnc_slider.pack(fill="x", pady=5)
        ttk.Label(tuning, text="Stricter                 More sensitive").pack(fill="x")
        self.pnc_readout = tk.StringVar()
        ttk.Label(tuning, textvariable=self.pnc_readout, wraplength=225).pack(fill="x", pady=4)
        ttk.Label(tuning, text="Preview uses saved nuclei. Save a new revision to keep these calls. Manual calls are retained.",
                  wraplength=225).pack(fill="x")
        if on_protocol:
            self.button(tuning, "Use for next analysis", self.use_pnc_protocol).pack(fill="x", pady=4)
        ttk.Label(sidebar, text="Select nuclei (Ctrl+click for multiple)", wraplength=225).pack(anchor="w")
        self.queue_filter = tk.StringVar(value="all")
        queue_filter = ttk.Combobox(sidebar, textvariable=self.queue_filter,
                                    values=("all", "unreviewed", "uncertain", "flagged", "rejected"),
                                    state="readonly", width=25)
        queue_filter.pack(fill="x", pady=3)
        queue_filter.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.button(sidebar, "Next in review queue", self.next_in_queue).pack(fill="x")
        self.listbox = tk.Listbox(sidebar, width=30, height=6, selectmode="extended", exportselection=False)
        self.listbox.pack(fill="x", pady=6)
        self.listbox.bind("<<ListboxSelect>>", self.select_list)
        self.list_ids = []
        self.detail = tk.StringVar(value="Select a nucleus to inspect its pixels and review state.")
        ttk.Label(sidebar, textvariable=self.detail, wraplength=225).pack(fill="x", pady=5)
        for label, command in (
            ("Reject / exclude", lambda: self.mark(rejected=True)),
            ("Accept / restore", lambda: self.mark(rejected=False)),
            ("Flag for follow-up", lambda: self.mark(flagged=True)),
            ("Clear flag", lambda: self.mark(flagged=False)),
            ("Confirm geometry + PNC", lambda: self.mark(reviewed=True)),
            ("Reviewer / note / PNC call", self.edit_details),
            ("Add verified reference", self.add_reference),
            ("Delete selected", self.delete), ("Merge selected", self.merge),
            ("Undo (Ctrl+Z)", self.undo), ("Redo (Ctrl+Y)", self.redo),
            ("Reset to original", self.reset), ("Save new revision", self.save),
        ):
            self.button(sidebar, label, command).pack(fill="x", pady=2)
        controls = ttk.Frame(self.window, padding=(8, 3))
        controls.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.button(controls, "Zoom +", lambda: self.zoom(1.25)).pack(side="left")
        self.button(controls, "Zoom -", lambda: self.zoom(0.8)).pack(side="left", padx=4)
        self.button(controls, "Fit image", self.fit).pack(side="left")
        ttk.Checkbutton(controls, text="Show masks", variable=self.show_masks, command=self.render).pack(side="left", padx=10)
        ttk.Checkbutton(controls, text="Show IDs", variable=self.show_ids, command=self.render).pack(side="left")
        self.status = tk.StringVar(value=self.session.warning or
            "Select: click nucleus. Outline: click vertices or drag freehand, then Enter. Wheel: zoom; middle drag: pan.")
        ttk.Label(self.window, textvariable=self.status, padding=8, wraplength=1100).grid(
            row=4, column=0, columnspan=2, sticky="ew")
        self.window.bind("<Return>", lambda _e: self.finish_outline())
        self.window.bind("<Escape>", lambda _e: self.cancel_outline())
        self.window.bind("<Control-z>", lambda _e: self.undo())
        self.window.bind("<Control-y>", lambda _e: self.redo())
        self.window.bind("<Control-s>", lambda _e: self.save())
        h, w = self.session.shape
        self.scale = min(1.0, 850 / w, 650 / h)
        self.refresh()
        self._poll_id = self.window.after(100, self.poll)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.buttons.append(widget)
        return widget

    def image_point(self, event):
        x, y = self.canvas.canvasx(event.x) / self.scale, self.canvas.canvasy(event.y) / self.scale
        h, w = self.session.shape
        return (x, y) if 0 <= x <= w - 1 and 0 <= y <= h - 1 else None

    def schedule_pnc_preview(self, _value=None):
        if self._syncing_pnc:
            return
        if self.points:
            self.status.set("Finish or cancel the outline before changing PNC settings.")
            return
        self._pnc_token += 1
        if self._pnc_after:
            self.window.after_cancel(self._pnc_after)
        self._pnc_after = self.window.after(180, self.launch_pnc_preview)

    def launch_pnc_preview(self):
        self._pnc_after = None
        mode = PNC_METHODS[self.pnc_method.get()]
        config = replace(self.session.config, pnc_mode=mode,
                         pnc_sensitivity=round(self.pnc_sensitivity.get(), 1))
        self.pnc_slider.configure(state="normal" if mode == "adaptive" else "disabled")
        self.pnc_readout.set(f"Sensitivity: {config.pnc_sensitivity:.1f} / 100" if mode == "adaptive"
                             else "Select Background-aware to use the slider. Legacy thresholds are in Advanced settings.")
        self._pending_pnc = (self._pnc_token, config)
        if self.busy or self._pnc_worker and self._pnc_worker.is_alive():
            return
        self._start_pending_pnc()

    def _start_pending_pnc(self):
        if not self._pending_pnc:
            return
        token, config = self._pending_pnc
        self._pending_pnc = None
        if config == self.session.config:
            return
        snapshot = copy.copy(self.session)
        snapshot.config = config
        self.busy = True
        for widget in self.buttons:
            widget.configure(state="disabled")
        self.status.set("Updating PNC candidates from saved nuclei; SAM is not being rerun...")

        def work():
            try:
                snapshot.counts()
                self.events.put(("pnc_preview", (token, snapshot, None)))
            except Exception as exc:
                self.events.put(("pnc_preview", (token, None, str(exc))))
        self._pnc_worker = threading.Thread(target=work, daemon=True)
        self._pnc_worker.start()

    def use_pnc_protocol(self):
        if self.busy or self._pnc_after or self._pending_pnc:
            return
        if self.on_protocol:
            self.on_protocol(self.session.config)
            self.status.set("PNC settings saved for future analyses. Save a new revision to keep this image's preview.")

    def click(self, event):
        if self.busy:
            return
        point = self.image_point(event)
        if point is None:
            return
        if self.tool.get() != "Select":
            if not self.points:
                self.tool_target = next(iter(self.selected)) if len(self.selected) == 1 else None
            self.points.append(point)
            self.draw_outline()
            return
        x, y = map(round, point)
        pixel = y * self.session.shape[1] + x
        hits = []
        for identifier, mask in self.session.masks.items():
            position = np.searchsorted(mask.pixels, pixel)
            if position < len(mask.pixels) and mask.pixels[position] == pixel:
                hits.append(identifier)
        found = min(hits, key=lambda i: (self.session.masks[i].rejected,
                                        len(self.session.masks[i].pixels)), default=None)
        if not event.state & 0x4:
            self.selected.clear()
        if found is not None:
            if found in self.selected:
                self.selected.remove(found)
            else:
                self.selected.add(found)
        self.refresh()

    def drag(self, event):
        if self.busy or self.tool.get() == "Select":
            return
        point = self.image_point(event)
        if point is not None and (not self.points or np.linalg.norm(np.array(point) - self.points[-1]) * self.scale >= 3):
            self.points.append(point)
            self.draw_outline()

    def remove_vertex(self, _event=None):
        if not self.busy and self.points:
            self.points.pop()
            self.draw_outline()

    def change_tool(self):
        self.points.clear()
        self.tool_target = None
        descriptions = {"Select": "Click nuclei; Ctrl+click selects multiple for merging.",
                        "Add": "Outline a missed nucleus, then Enter. Manual masks bypass automatic area limits.",
                        "Redraw": "Select one nucleus first, then outline its replacement boundary and press Enter.",
                        "Split": "Select one nucleus first; outline ONE part, then Enter. The remaining pixels become the other nucleus."}
        self.status.set(descriptions[self.tool.get()])
        self.draw_outline()

    def finish_outline(self):
        if self.busy or self.tool.get() == "Select":
            return
        try:
            tool = self.tool.get()
            if tool == "Add":
                self.selected = {self.session.add(self.points)}
            else:
                if self.tool_target not in self.session.masks:
                    raise ValueError("Select exactly one nucleus before drawing")
                if tool == "Redraw":
                    self.session.redraw(self.tool_target, self.points)
                else:
                    self.selected = set(self.session.split(self.tool_target, self.points))
            self.points.clear()
            self.tool.set("Select")
            self.status.set("Correction applied. Counts updated; save a revision to keep your changes.")
            self.refresh()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Outline", str(exc), parent=self.window)

    def cancel_outline(self):
        if not self.busy:
            self.points.clear()
            self.tool_target = None
            self.tool.set("Select")
            self.draw_outline()

    def action(self, operation):
        if self.busy:
            return
        if self.points:
            messagebox.showinfo("Unfinished outline", "Finish or cancel your outline first.", parent=self.window)
            return
        try:
            operation()
            self.selected.intersection_update(self.session.masks)
            self.refresh()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Correction", str(exc), parent=self.window)

    def mark(self, **changes):
        self.action(lambda: self.session.mark(sorted(self.selected), **changes))

    def delete(self):
        self.action(lambda: self.session.delete(sorted(self.selected)))

    def merge(self):
        def operation():
            self.selected = {self.session.merge(self.selected)}
        self.action(operation)

    def undo(self):
        self.action(self.session.undo)

    def redo(self):
        self.action(self.session.redo)

    def reset(self):
        self.action(self.session.reset)

    def refresh(self):
        self._syncing_pnc = True
        self.pnc_method.set(next(k for k, v in PNC_METHODS.items() if v == self.session.config.pnc_mode))
        self.pnc_sensitivity.set(self.session.config.pnc_sensitivity)
        adaptive = self.session.config.pnc_mode == "adaptive"
        self.pnc_slider.configure(state="normal" if adaptive else "disabled")
        self.pnc_readout.set(f"Sensitivity: {self.session.config.pnc_sensitivity:.1f} / 100" if adaptive
                             else "Select Background-aware to use the slider. Legacy thresholds are in Advanced settings.")
        self._syncing_pnc = False
        counts, details = self.session.counts()
        percent = f"{counts['percentage']:.2f}%" if counts["percentage"] is not None else "N/A"
        self.stats.set(f"PNC+ {counts['n_positive']} / {counts['n_total']} ({percent})   "
                       f"Rejected: {counts['n_bad']}   Flagged: {counts['n_flagged']}   "
                       f"Mode: {self.session.config.pnc_mode}   "
                       f"{'Unsaved changes' if self.session.dirty else 'Saved/original'}")
        self.listbox.delete(0, "end")
        queue = self.session.review_queue(self.queue_filter.get())
        self.list_ids = [row["MaskID"] for row in queue]
        for index, identifier in enumerate(self.list_ids):
            mask = self.session.masks[identifier]
            state = "excluded" if details[identifier]["rejected"] else "PNC+" if details[identifier]["positive"] else "PNC-"
            self.listbox.insert("end", f"{identifier}: {state}{' [flag]' if mask.flagged else ''}{' [done]' if mask.reviewed else ''}")
            if identifier in self.selected:
                self.listbox.selection_set(index)
        if len(self.selected) == 1:
            identifier = next(iter(self.selected))
            mask = self.session.masks[identifier]
            self.detail.set(f"Nucleus {identifier}\nArea: {len(mask.pixels)} px\n"
                            f"Positive PNC pixels: {details[identifier]['positive_pixels']}\n"
                            f"PNC spots: {details[identifier]['spots']}\n"
                            + (f"Relative PNC signal score: {details[identifier]['signal_score']:.1f}\n"
                               if "signal_score" in details[identifier] else "") +
                            f"PNC call: {'automatic' if mask.pnc_override is None else 'manual positive' if mask.pnc_override else 'manual negative'}\n"
                            f"{'Verified' if mask.reviewed else 'Awaiting verification'}\n"
                            f"{'Manually edited' if mask.edited else 'Original boundary'}\n"
                            + "\n".join(next((r["reasons"] for r in self.session.review_queue("all")
                                               if r["MaskID"] == identifier), [])))
        else:
            self.detail.set(f"{len(self.selected)} nuclei selected. Ctrl+click to select multiple.\n"
                            "Green = selected; yellow = flagged; gray = rejected.")
        self.render()

    def select_list(self, _event=None):
        if not self.busy and not self.points:
            chosen = {self.list_ids[i] for i in self.listbox.curselection()}
            if chosen != self.selected:
                self.selected = chosen
                self.refresh()

    def next_in_queue(self):
        if self.busy or self.points:
            return
        queue = self.session.review_queue(self.queue_filter.get())
        if not queue:
            self.status.set("No nuclei in this review queue.")
            return
        ids = [row["MaskID"] for row in queue]
        current = next(iter(self.selected)) if len(self.selected) == 1 else None
        identifier = ids[(ids.index(current) + 1) % len(ids)] if current in ids else ids[0]
        self.selected = {identifier}
        self.scale = max(1, self.scale)
        self.refresh()
        yy, xx = np.unravel_index(self.session.masks[identifier].pixels, self.session.shape)
        h, w = self.session.shape
        self.canvas.xview_moveto(max(0, (xx.mean() * self.scale - self.canvas.winfo_width() / 2) / (w * self.scale)))
        self.canvas.yview_moveto(max(0, (yy.mean() * self.scale - self.canvas.winfo_height() / 2) / (h * self.scale)))

    def edit_details(self):
        if self.busy or self.points or len(self.selected) != 1:
            messagebox.showinfo("Review details", "Select exactly one nucleus and finish any outline first.", parent=self.window)
            return
        identifier = next(iter(self.selected))
        mask = self.session.masks[identifier]
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Review details - nucleus {identifier}")
        dialog.transient(self.window)
        dialog.grab_set()
        reviewer = tk.StringVar(value=self.session.reviewer)
        call = tk.StringVar(value="automatic" if mask.pnc_override is None else "positive" if mask.pnc_override else "negative")
        ttk.Label(dialog, text="Reviewer name").pack(anchor="w", padx=10, pady=5)
        ttk.Entry(dialog, textvariable=reviewer, width=45).pack(padx=10)
        ttk.Label(dialog, text="PNC call (overrides automatic classification)").pack(anchor="w", padx=10, pady=5)
        ttk.Combobox(dialog, textvariable=call, values=("automatic", "positive", "negative"), state="readonly").pack(padx=10)
        ttk.Label(dialog, text="Reason / note").pack(anchor="w", padx=10, pady=5)
        notes = tk.Text(dialog, height=5, width=50)
        notes.pack(padx=10)
        notes.insert("1.0", mask.note)

        def apply():
            self.session.reviewer = reviewer.get().strip()
            self.action(lambda: self.session.mark([identifier], note=notes.get("1.0", "end-1c"),
                        pnc_override={"automatic": None, "positive": True, "negative": False}[call.get()]))
            dialog.destroy()
        ttk.Button(dialog, text="Apply (then confirm after checking)", command=apply).pack(pady=10)

    def add_reference(self):
        if self.busy or self.points:
            return
        from .benchmark import add_reference, projection_digest

        reviewer = simpledialog.askstring("Verified reference", "Reviewer name", initialvalue=self.session.reviewer,
                                          parent=self.window)
        if not reviewer:
            return
        group = simpledialog.askstring("Verified reference", "Specimen/acquisition group (kept within one split)", parent=self.window)
        if not group:
            return
        split = simpledialog.askstring("Verified reference", "Split: validation or test", initialvalue="test", parent=self.window)
        if not split:
            return
        folder = filedialog.askdirectory(title="Reference-set folder", mustexist=False, parent=self.window)
        if not folder:
            return
        self.session.reviewer = reviewer.strip()
        self.busy = True
        for widget in self.buttons:
            widget.configure(state="disabled")
        self.status.set("Saving and registering a verified reference...")

        def worker():
            try:
                path = add_reference(self.session, folder, split=split.strip(), group=group)
                document = json.loads(path.read_text(encoding="utf-8"))
                identity = projection_digest(self.session.projections)
                case = next(case for case in document["cases"] if case["image_sha256"] == identity)
                revision = path.parent / case["review_directory"].replace("\\", "/")
                self.events.put(("reference", (revision, self.session.counts()[0], path)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def render(self):
        image = render_review(self.session, self.selected, self.channel.get(), self.show_masks.get())
        w, h = image.size
        size = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))
        image = image.resize(size, Image.Resampling.NEAREST if self.scale > 1 else Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        self.canvas.delete("background")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags="background")
        self.canvas.tag_lower("background")
        self.canvas.configure(scrollregion=(0, 0, *size))
        self.canvas.delete("ids")
        self.canvas.delete("spots")
        if self.session.config.pnc_mode in ("spots", "adaptive") and self.show_masks.get():
            for spot in self.session._spot_rows:
                x, y = (spot["CentroidX"] - 1) * self.scale, (spot["CentroidY"] - 1) * self.scale
                self.canvas.create_oval(x - 4, y - 4, x + 4, y + 4, outline="#40ff80", width=2, tags="spots")
        if self.show_ids.get():
            for identifier, mask in self.session.masks.items():
                yy, xx = np.unravel_index(mask.pixels, self.session.shape)
                self.canvas.create_text(float(xx.mean()) * self.scale, float(yy.mean()) * self.scale,
                                         text=str(identifier), fill="white", tags="ids")
        self.draw_outline()

    def draw_outline(self):
        self.canvas.delete("outline")
        if self.points:
            coordinates = [coordinate * self.scale for point in self.points for coordinate in point]
            if len(self.points) > 1:
                self.canvas.create_line(*coordinates, fill="#ffff40", width=2, tags="outline")
            for x, y in self.points:
                x, y = x * self.scale, y * self.scale
                self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#ffff40", tags="outline")

    def wheel(self, event):
        self.zoom(1.25 if event.delta > 0 else 0.8, event)

    def zoom(self, factor, event=None):
        old_scale = self.scale
        x = event.x if event else self.canvas.winfo_width() / 2
        y = event.y if event else self.canvas.winfo_height() / 2
        px, py = self.canvas.canvasx(x) / old_scale, self.canvas.canvasy(y) / old_scale
        self.scale = min(8.0, max(0.1, self.scale * factor))
        self.render()
        h, w = self.session.shape
        self.canvas.xview_moveto(max(0, (px * self.scale - x) / (w * self.scale)))
        self.canvas.yview_moveto(max(0, (py * self.scale - y) / (h * self.scale)))

    def fit(self):
        h, w = self.session.shape
        self.scale = min(8, max(0.1, min(self.canvas.winfo_width() / w, self.canvas.winfo_height() / h)))
        self.render()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def save(self):
        if self.busy or self._pnc_after or self._pending_pnc:
            return
        if self.points:
            messagebox.showinfo("Unfinished outline", "Finish or cancel your outline before saving.", parent=self.window)
            return
        folder = filedialog.askdirectory(title="Save a new review revision in this folder",
                                          initialdir=str(self.directory / "reviews"), parent=self.window,
                                          mustexist=False)
        if not folder:
            return
        self.save_to(folder)

    def save_to(self, folder):
        if self.busy or self._pnc_after or self._pending_pnc:
            return
        self.busy = True
        self.pnc_method_box.configure(state="disabled")
        self.pnc_slider.configure(state="disabled")
        for widget in self.buttons:
            widget.configure(state="disabled")
        self.status.set("Measuring corrected nuclei and saving a new revision...")

        def worker():
            try:
                self.events.put(("saved", self.session.save(folder)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.pnc_method_box.configure(state="readonly")
            for widget in self.buttons:
                widget.configure(state="normal")
            if kind == "pnc_preview":
                token, preview, error = payload
                if preview is not None:
                    # Even an obsolete slider response can warm the immutable
                    # geometry cache. Only the newest request changes calls.
                    for name in ("_adaptive_features", "_adaptive_geometry_key", "_adaptive_source_masks"):
                        setattr(self.session, name, getattr(preview, name))
                if token == self._pnc_token:
                    if error:
                        self.status.set(f"PNC preview failed: {error}")
                    else:
                        self.session.set_pnc_config(preview.config, preview)
                        self.status.set("PNC preview updated. Review candidates and save a new revision to keep changes.")
                        self.refresh()
            elif kind in ("saved", "reference"):
                directory, stats = payload[:2]
                self.directory = directory
                self.status.set(f"Verified reference registered: {payload[2]}" if kind == "reference"
                                else f"Saved new revision: {directory}")
                self.refresh()
                if self.on_saved:
                    self.on_saved(directory, stats)
            else:
                self.status.set("Save failed; edits remain available. Choose a writable folder and retry.")
                messagebox.showerror("Save revision", payload, parent=self.window)
                self.refresh()
        if not self.busy and self._pending_pnc and not (self._pnc_worker and self._pnc_worker.is_alive()):
            self._start_pending_pnc()
        self._poll_id = self.window.after(100, self.poll)

    def close(self):
        if self.busy or self._pnc_worker and self._pnc_worker.is_alive():
            messagebox.showinfo("Saving", "Wait for the revision to finish saving before closing.", parent=self.window)
            return
        if self.session.dirty or self.points:
            if not messagebox.askyesno("Unsaved corrections", "Close and discard unsaved corrections?", parent=self.window):
                return
        self.window.after_cancel(self._poll_id)
        if self._pnc_after:
            self.window.after_cancel(self._pnc_after)
        self.window.destroy()
