"""Lightweight Tk nucleus review window with polygon and freehand corrections."""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk
from scipy import ndimage as ndi

from .imaging import scale_uint8
from .review import ReviewSession


def render_review(session, selected=(), channel="DAPI", show_masks=True):
    """Render masks in original pixel coordinates, including flagged/rejected objects."""
    dapi = session.projections.dapi_max
    if channel == "DAPI + PNC":
        base = np.stack([scale_uint8(session.projections.pnc_max), dapi // 3, dapi], axis=-1)
    else:
        gray = {"DAPI": dapi, "PNC": scale_uint8(session.projections.pnc_max),
                "PNC threshold": session._positive_pixels.astype(np.uint8) * 255}[channel]
        base = np.repeat(gray[..., None], 3, axis=-1)
    if not show_masks:
        return Image.fromarray(base)
    _, details = session.counts()
    selected = set(selected)
    order = sorted(session.masks, key=lambda i: (i in selected, not session.masks[i].rejected, i))
    flat = base.reshape(-1, 3)
    for identifier in order:
        mask = session.masks[identifier]
        color = ((180, 180, 180) if mask.rejected else
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
    def __init__(self, parent, directory, on_saved=None):
        self.session = ReviewSession.open(directory)
        self.directory = Path(directory).resolve()
        self.on_saved = on_saved
        self.selected = set()
        self.points = []
        self.tool_target = None
        self.busy = False
        self.events = queue.Queue()
        self.photo = None
        self.window = tk.Toplevel(parent)
        self.window.title(f"Review nuclei - {self.directory.name}")
        self.window.geometry("1180x820")
        self.window.minsize(950, 720)
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
        sidebar = ttk.Frame(self.window, padding=8)
        sidebar.grid(row=2, column=1, sticky="ns")
        ttk.Label(sidebar, text="Select nuclei (Ctrl+click for multiple)", wraplength=225).pack(anchor="w")
        self.listbox = tk.Listbox(sidebar, width=30, height=9, selectmode="extended", exportselection=False)
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
        counts, details = self.session.counts()
        percent = f"{counts['percentage']:.2f}%" if counts["percentage"] is not None else "N/A"
        self.stats.set(f"PNC+ {counts['n_positive']} / {counts['n_total']} ({percent})   "
                       f"Rejected: {counts['n_bad']}   Flagged: {counts['n_flagged']}   "
                       f"Cutoff: {self.session.config.positive_threshold} px   "
                       f"{'Unsaved changes' if self.session.dirty else 'Saved/original'}")
        self.listbox.delete(0, "end")
        self.list_ids = sorted(self.session.masks)
        for index, identifier in enumerate(self.list_ids):
            mask = self.session.masks[identifier]
            state = "rejected" if mask.rejected else "PNC+" if details[identifier]["positive"] else "PNC-"
            self.listbox.insert("end", f"{identifier}: {state}{' [flag]' if mask.flagged else ''}")
            if identifier in self.selected:
                self.listbox.selection_set(index)
        if len(self.selected) == 1:
            identifier = next(iter(self.selected))
            mask = self.session.masks[identifier]
            self.detail.set(f"Nucleus {identifier}\nArea: {len(mask.pixels)} px\n"
                            f"Positive PNC pixels: {details[identifier]['positive_pixels']}\n"
                            f"{'Manually edited' if mask.edited else 'Original boundary'}\n"
                            "Flagging keeps it counted; rejecting excludes it.")
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
        if self.busy:
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
        self.busy = True
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
            for widget in self.buttons:
                widget.configure(state="normal")
            if kind == "saved":
                directory, stats = payload
                self.directory = directory
                self.status.set(f"Saved new revision: {directory}")
                self.refresh()
                if self.on_saved:
                    self.on_saved(directory, stats)
            else:
                self.status.set("Save failed; edits remain available. Choose a writable folder and retry.")
                messagebox.showerror("Save revision", payload, parent=self.window)
        self._poll_id = self.window.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Saving", "Wait for the revision to finish saving before closing.", parent=self.window)
            return
        if self.session.dirty or self.points:
            if not messagebox.askyesno("Unsaved corrections", "Close and discard unsaved corrections?", parent=self.window):
                return
        self.window.after_cancel(self._poll_id)
        self.window.destroy()
