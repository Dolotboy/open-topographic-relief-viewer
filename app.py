"""Turn an image into an interactive 3D relief surface."""
from __future__ import annotations

import copy
import json
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageTk
from scipy import ndimage
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import is_color_like, rgb_to_hsv
from matplotlib.figure import Figure


DEFAULT_CONFIG = {
    "background": {"light": "#f5f7fa", "black": "#000000"},
    "display": {"max_side": 220, "height_smoothing": 5.0},
    "elevation": {"slider_max": 100, "initial_with_contour_interval": 1.0},
    "contours": {
        "color_tolerance": 35,
        "color_tolerance_max": 150,
        "minimum_component_pixels": 12,
        "closing_size": 3,
        "stitch_max_gap_px": 160,
        "stitch_residual_min_px": 8.0,
        "stitch_residual_gap_ratio": 0.6,
        "stitch_residual_extra_px": 5.0,
        "stitch_max_slope_delta": 2.0,
        "stitch_slope_weight": 2.0,
        "stitch_gap_weight": 0.02,
        "hue_tolerance_scale": 0.25,
        "hue_tolerance_min": 0.025,
        "hue_tolerance_max": 0.12,
        "minimum_saturation_target_fraction": 0.15,
        "minimum_saturation_floor": 0.08,
    },
}


def load_config() -> dict:
    """Read config.json and fill any omitted options with built-in defaults."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = Path(__file__).with_name("config.json")
    try:
        user_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return config
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read {config_path.name}: {exc}") from exc
    if not isinstance(user_config, dict):
        raise ValueError("config.json must contain a JSON object")
    for section, values in user_config.items():
        if section in config and isinstance(values, dict):
            config[section].update(values)
    for key in ("light", "black"):
        if not is_color_like(config["background"].get(key)):
            config["background"][key] = DEFAULT_CONFIG["background"][key]
    config["display"]["max_side"] = max(32, int(config["display"]["max_side"]))
    config["display"]["height_smoothing"] = max(0.0, float(config["display"]["height_smoothing"]))
    config["elevation"]["slider_max"] = max(1, int(config["elevation"]["slider_max"]))
    config["elevation"]["initial_with_contour_interval"] = max(0.0, float(config["elevation"]["initial_with_contour_interval"]))
    config["contours"]["color_tolerance"] = max(0, int(config["contours"]["color_tolerance"]))
    config["contours"]["color_tolerance_max"] = max(1, int(config["contours"]["color_tolerance_max"]))
    for key in ("minimum_component_pixels", "closing_size", "stitch_max_gap_px"):
        config["contours"][key] = max(1, int(config["contours"][key]))
    for key in (
        "stitch_residual_min_px", "stitch_residual_gap_ratio", "stitch_residual_extra_px",
        "stitch_max_slope_delta", "stitch_slope_weight", "stitch_gap_weight",
        "hue_tolerance_scale", "hue_tolerance_min", "hue_tolerance_max",
        "minimum_saturation_target_fraction", "minimum_saturation_floor",
    ):
        config["contours"][key] = max(0.0, float(config["contours"][key]))
    return config


class ReliefApp:
    MAX_SIDE = 220
    HEIGHT_SMOOTHING = 5.0

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        try:
            self.config = load_config()
        except (ValueError, TypeError) as exc:
            messagebox.showwarning("Invalid configuration", f"{exc}\nUsing built-in defaults.", parent=root)
            self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.MAX_SIDE = self.config["display"]["max_side"]
        self.HEIGHT_SMOOTHING = self.config["display"]["height_smoothing"]
        self.background_colors = self.config["background"]
        root.title("Image to 3D Relief")
        root.geometry("1100x760")
        root.minsize(760, 560)
        self.image: Image.Image | None = None
        self.color_image: Image.Image | None = None
        self.filename = ""
        self.black_background = tk.BooleanVar(value=False)
        self.elevation = tk.DoubleVar(value=0.0)
        self.invert_elevation = tk.BooleanVar(value=False)
        self.contour_color: tuple[int, int, int] | None = None
        self.contour_interval: float | None = None
        self.contour_tolerance = tk.IntVar(value=self.config["contours"]["color_tolerance"])
        self.contour_components: list[tuple[np.ndarray, np.ndarray]] = []
        self.selected_contour_index = 0
        self.manual_contour_values: dict[int, float] = {}
        self._updating_manual_value = False
        self._build_ui()
        self._draw_empty()

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="3D Relief from an Image", font=("TkDefaultFont", 18, "bold")).pack(side="left")
        self.background_button = ttk.Button(
            header,
            text="Black background",
            command=self._toggle_background,
        )
        self.background_button.pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Choose an image…", command=self.open_image).pack(side="right")
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Elevation", font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 10))
        self.slider = ttk.Scale(controls, from_=0, to=self.config["elevation"]["slider_max"], variable=self.elevation, command=self._slider_changed)
        self.slider.pack(side="left", fill="x", expand=True, padx=6)
        self.value_label = ttk.Label(controls, text="0.00×", width=7, anchor="e")
        self.value_label.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            outer,
            text="Invert elevation",
            variable=self.invert_elevation,
            command=self._invert_changed,
        ).pack(anchor="w", pady=(0, 8))
        contour = ttk.LabelFrame(outer, text="Contour-line detection (optional)", padding=(8, 5))
        contour.pack(fill="x", pady=(0, 8))
        self.contour_button = ttk.Button(contour, text="Choose contour color…", command=self._choose_contour_color)
        self.contour_button.pack(side="left")
        self.sample_color_button = ttk.Button(contour, text="Pick from image…", command=self._pick_color_from_image, state="disabled")
        self.sample_color_button.pack(side="left", padx=(6, 0))
        ttk.Label(contour, text="Color tolerance").pack(side="left", padx=(12, 4))
        self.tolerance_slider = ttk.Scale(contour, from_=0, to=self.config["contours"]["color_tolerance_max"], variable=self.contour_tolerance, command=self._tolerance_changed)
        self.tolerance_slider.pack(side="left", fill="x", expand=True, padx=4)
        self.tolerance_label = ttk.Label(contour, text="35", width=4, anchor="e")
        self.tolerance_label.pack(side="left")
        self.contour_label = ttk.Label(contour, text="No color selected; using image brightness")
        self.contour_label.pack(anchor="w", pady=(5, 0))
        manual = ttk.LabelFrame(outer, text="Manual contour altitude", padding=(8, 5))
        manual.pack(fill="x", pady=(0, 8))
        self.previous_contour_button = ttk.Button(manual, text="◀", width=3, command=self._previous_contour)
        self.previous_contour_button.pack(side="left")
        self.contour_counter = ttk.Label(manual, text="0 / 0", width=9, anchor="center")
        self.contour_counter.pack(side="left", padx=5)
        self.next_contour_button = ttk.Button(manual, text="▶", width=3, command=self._next_contour)
        self.next_contour_button.pack(side="left")
        ttk.Label(manual, text="Altitude (m)").pack(side="left", padx=(14, 5))
        self.manual_value_var = tk.StringVar()
        self.manual_value_entry = ttk.Entry(manual, textvariable=self.manual_value_var, width=12)
        self.manual_value_entry.pack(side="left")
        self.manual_value_var.trace_add("write", self._manual_value_changed)
        self.manual_status = ttk.Label(manual, text="Choose a contour color to detect lines", foreground="#666")
        self.manual_status.pack(side="left", padx=10)
        self._update_manual_controls()
        self.file_label = ttk.Label(outer, text="No image selected", foreground="#666")
        self.file_label.pack(anchor="w", pady=(0, 6))
        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor="#f5f7fa")
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.fig.subplots_adjust(left=0.02, right=0.98, bottom=0.03, top=0.96)
        self.canvas = FigureCanvasTkAgg(self.fig, master=outer)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.bind("<MouseWheel>", self._zoom_with_wheel)
        canvas_widget.bind("<Button-4>", self._zoom_with_wheel)
        canvas_widget.bind("<Button-5>", self._zoom_with_wheel)
        ttk.Label(outer, text="Tip: drag to rotate; use the mouse wheel to zoom.", foreground="#666").pack(anchor="w", pady=(8, 0))

    def _zoom_with_wheel(self, event) -> None:
        if self.image is None:
            return
        delta = getattr(event, "delta", 0)
        direction = 1 if delta > 0 or getattr(event, "num", None) == 4 else -1
        if not delta and getattr(event, "num", None) not in (4, 5):
            return
        factor = 0.85 if direction > 0 else 1 / 0.85
        for get_limits, set_limits in (
            (self.ax.get_xlim3d, self.ax.set_xlim3d),
            (self.ax.get_ylim3d, self.ax.set_ylim3d),
            (self.ax.get_zlim3d, self.ax.set_zlim3d),
        ):
            low, high = get_limits()
            center = (low + high) / 2
            half_range = (high - low) * factor / 2
            set_limits(center - half_range, center + half_range)
        self.canvas.draw_idle()

    def _toggle_background(self) -> None:
        use_black = not self.black_background.get()
        self.black_background.set(use_black)
        self.background_button.configure(
            text="Light background" if use_black else "Black background"
        )
        if self.image is None:
            self._draw_empty()
        else:
            self._render_surface()

    def _apply_plot_background(self) -> None:
        background = self.background_colors["black"] if self.black_background.get() else self.background_colors["light"]
        self.fig.set_facecolor(background)
        self.ax.set_facecolor(background)
        if self.black_background.get():
            for axis in (self.ax.xaxis, self.ax.yaxis, self.ax.zaxis):
                axis.set_pane_color("#000000")
                axis.pane.set_edgecolor("#ffffff")
                axis.label.set_color("#ffffff")
            self.ax.tick_params(axis="x", colors="#ffffff")
            self.ax.tick_params(axis="y", colors="#ffffff")
            self.ax.tick_params(axis="z", colors="#ffffff")
            self.ax.title.set_color("#ffffff")

    def open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif"), ("All files", "*.*")],
        )
        if not path:
            return
        interval = simpledialog.askstring(
            "Contour interval",
            "Vertical contour interval in meters (for example, 1 or 5).\n"
            "Leave blank if unknown. This is the elevation difference between adjacent contour lines.",
            parent=self.root,
        )
        if interval is None:
            return
        interval = interval.strip()
        if interval:
            try:
                self.contour_interval = float(interval.replace(",", "."))
                if self.contour_interval <= 0:
                    raise ValueError
            except ValueError:
                self.contour_interval = None
                messagebox.showerror("Invalid contour interval", "Enter a positive number or leave the field blank.", parent=self.root)
                return
        else:
            self.contour_interval = None
        try:
            with Image.open(path) as source:
                # Flatten transparency onto white before deriving heights.
                # Otherwise transparent PNG pixels often become black and
                # create a false low basin around the actual map.
                rgba = source.convert("RGBA")
                white_background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                flattened = Image.alpha_composite(white_background, rgba).convert("RGB")
                self.image = ImageOps.grayscale(flattened).copy()
                self.color_image = flattened.copy()
            self.filename = path
            self.sample_color_button.configure(state="normal")
            self.manual_contour_values.clear()
            self.selected_contour_index = 0
            self._refresh_contour_components()
            # A supplied contour interval should have a visible effect on load.
            # Blank intervals retain the original flat-on-load behavior.
            initial_elevation = self.config["elevation"]["initial_with_contour_interval"] if self.contour_interval is not None else 0.0
            self.elevation.set(initial_elevation)
            self.value_label.configure(text=f"{initial_elevation:.2f}×")
            self.file_label.configure(text=f"{Path(path).name}  ·  {self.image.width} × {self.image.height} px")
            self._render_surface()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open image", str(exc), parent=self.root)

    def _choose_contour_color(self) -> None:
        result = colorchooser.askcolor(title="Choose the contour-line color", parent=self.root)
        if result[0] is None:
            return
        self._set_contour_color(tuple(int(round(channel)) for channel in result[0]), result[1])

    def _set_contour_color(self, color: tuple[int, int, int], label: str) -> None:
        self.contour_color = color
        self.contour_button.configure(text=f"Contour color: {label}")
        self.contour_label.configure(text="Selected pixels define the contour distance field")
        if self.image is not None:
            self.manual_contour_values.clear()
            self.selected_contour_index = 0
            self._refresh_contour_components()
            self._render_surface()

    def _pick_color_from_image(self) -> None:
        if self.color_image is None:
            return
        picker = tk.Toplevel(self.root)
        picker.title("Pick contour color from image")
        picker.transient(self.root)
        picker.geometry("1100x780")
        picker.columnconfigure(0, weight=1)
        picker.rowconfigure(1, weight=1)
        initial_scale = min(1.0, 1000 / self.color_image.width, 650 / self.color_image.height)
        zoom = [initial_scale]
        preview_width = max(1, round(self.color_image.width * zoom[0]))
        preview_height = max(1, round(self.color_image.height * zoom[0]))
        preview = self.color_image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(preview)
        photo_ref = [photo]
        controls = ttk.Frame(picker, padding=(8, 6))
        controls.grid(row=0, column=0, columnspan=2, sticky="ew")
        canvas = tk.Canvas(picker, background="#222", highlightthickness=0, cursor="crosshair", width=1000, height=650)
        canvas.grid(row=1, column=0, sticky="nsew")
        vertical_scroll = ttk.Scrollbar(picker, orient="vertical", command=canvas.yview)
        vertical_scroll.grid(row=1, column=1, sticky="ns")
        horizontal_scroll = ttk.Scrollbar(picker, orient="horizontal", command=canvas.xview)
        horizontal_scroll.grid(row=2, column=0, sticky="ew")
        canvas.configure(xscrollcommand=horizontal_scroll.set, yscrollcommand=vertical_scroll.set)
        image_item = canvas.create_image(0, 0, anchor="nw", image=photo_ref[0])
        canvas.configure(scrollregion=(0, 0, preview_width, preview_height))
        zoom_label = ttk.Label(controls, text=f"{zoom[0] * 100:.0f}%")
        zoom_label.pack(side="left", padx=8)
        ttk.Label(controls, text="Use the wheel or +/− to zoom; click a contour to sample its color").pack(side="left", padx=12)

        def set_zoom(new_zoom: float, anchor_x: float, anchor_y: float) -> None:
            old_width = max(1, round(self.color_image.width * zoom[0]))
            old_height = max(1, round(self.color_image.height * zoom[0]))
            image_x = canvas.canvasx(anchor_x) * self.color_image.width / old_width
            image_y = canvas.canvasy(anchor_y) * self.color_image.height / old_height
            zoom[0] = min(initial_scale * 12, max(initial_scale * 0.25, new_zoom))
            new_width = max(1, round(self.color_image.width * zoom[0]))
            new_height = max(1, round(self.color_image.height * zoom[0]))
            resized = self.color_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo_ref[0] = ImageTk.PhotoImage(resized)
            canvas.itemconfigure(image_item, image=photo_ref[0])
            canvas.configure(scrollregion=(0, 0, new_width, new_height))
            canvas.update_idletasks()
            max_x = max(0, new_width - canvas.winfo_width())
            max_y = max(0, new_height - canvas.winfo_height())
            canvas.xview_moveto(min(1, max(0, image_x * zoom[0] - anchor_x) / max(1, new_width)))
            canvas.yview_moveto(min(1, max(0, image_y * zoom[0] - anchor_y) / max(1, new_height)))
            # Clamp view offsets after zooming near an image edge.
            canvas.xview_moveto(min(max_x, max(0, canvas.canvasx(0))) / max(1, new_width))
            canvas.yview_moveto(min(max_y, max(0, canvas.canvasy(0))) / max(1, new_height))
            zoom_label.configure(text=f"{zoom[0] / initial_scale * 100:.0f}%")

        def zoom_button(multiplier: float) -> None:
            set_zoom(zoom[0] * multiplier, canvas.winfo_width() / 2, canvas.winfo_height() / 2)

        ttk.Button(controls, text="−", width=3, command=lambda: zoom_button(1 / 1.25)).pack(side="left")
        ttk.Button(controls, text="+", width=3, command=lambda: zoom_button(1.25)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Fit", command=lambda: set_zoom(initial_scale, 0, 0)).pack(side="left", padx=(4, 0))

        def on_wheel(event: tk.Event) -> None:
            delta = getattr(event, "delta", 0)
            direction = 1 if delta > 0 or getattr(event, "num", None) == 4 else -1
            if delta or getattr(event, "num", None) in (4, 5):
                set_zoom(zoom[0] * (1.25 if direction > 0 else 1 / 1.25), event.x, event.y)

        canvas.bind("<MouseWheel>", on_wheel)
        canvas.bind("<Button-4>", on_wheel)
        canvas.bind("<Button-5>", on_wheel)

        def sample(event: tk.Event) -> None:
            x = int(canvas.canvasx(event.x) * self.color_image.width / max(1, round(self.color_image.width * zoom[0])))
            y = int(canvas.canvasy(event.y) * self.color_image.height / max(1, round(self.color_image.height * zoom[0])))
            if not (0 <= x < self.color_image.width and 0 <= y < self.color_image.height):
                return
            color = self.color_image.getpixel((x, y))
            self._set_contour_color(color, "#%02x%02x%02x" % color)
            picker.destroy()

        canvas.bind("<Button-1>", sample)

    def _tolerance_changed(self, _value: str) -> None:
        tolerance = int(round(self.contour_tolerance.get()))
        self.contour_tolerance.set(tolerance)
        self.tolerance_label.configure(text=str(tolerance))
        if self.image is not None and self.contour_color is not None:
            self._refresh_contour_components()
            self._render_surface()

    def _refresh_contour_components(self) -> None:
        previous_count = len(self.contour_components)
        self.contour_components = []
        if self.color_image is not None and self.contour_color is not None:
            rgb = np.asarray(self.color_image, dtype=np.float32)
            mask = self._contour_color_mask(rgb)
            # Close only tiny raster gaps here. Longer breaks (often where
            # elevation labels cover a contour) are linked by endpoint tracking below.
            closing_size = self.config["contours"]["closing_size"]
            mask = ndimage.binary_closing(mask, structure=np.ones((closing_size, closing_size), dtype=bool))
            labels, _ = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
            fragments: list[tuple[np.ndarray, np.ndarray]] = []
            for label_id, bounds in enumerate(ndimage.find_objects(labels), start=1):
                if bounds is None:
                    continue
                ys, xs = np.where(labels[bounds] == label_id)
                if len(xs) < self.config["contours"]["minimum_component_pixels"]:
                    continue
                ys = ys + bounds[0].start
                xs = xs + bounds[1].start
                fragments.append((ys.astype(np.int32), xs.astype(np.int32)))
            self.contour_components = self._join_contour_fragments(fragments)
        if previous_count and len(self.contour_components) != previous_count:
            self.manual_contour_values.clear()
        if self.contour_components:
            self.selected_contour_index = min(self.selected_contour_index, len(self.contour_components) - 1)
        else:
            self.selected_contour_index = 0
        self._update_manual_controls()

    def _join_contour_fragments(
        self,
        fragments: list[tuple[np.ndarray, np.ndarray]],
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Join broken contour segments when their nearby endpoints continue smoothly."""
        if len(fragments) < 2:
            return fragments

        count = len(fragments)
        parent = list(range(count))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(first: int, second: int) -> None:
            first_root, second_root = find(first), find(second)
            if first_root != second_root:
                parent[second_root] = first_root

        bounds: list[tuple[int, int, float, float, float, float]] = []
        for ys, xs in fragments:
            order = np.argsort(ys, kind="stable")
            sorted_y, sorted_x = ys[order], xs[order]
            unique_y, inverse = np.unique(sorted_y, return_inverse=True)
            row_x = np.asarray([np.median(sorted_x[inverse == row]) for row in range(len(unique_y))])
            first_count = max(1, min(len(unique_y), 12))
            last_count = first_count
            first_slope = float(np.polyfit(unique_y[:first_count], row_x[:first_count], 1)[0]) if first_count > 1 else 0.0
            last_slope = float(np.polyfit(unique_y[-last_count:], row_x[-last_count:], 1)[0]) if last_count > 1 else 0.0
            bounds.append((
                int(unique_y[0]),
                int(unique_y[-1]),
                float(np.median(row_x[:first_count])),
                float(np.median(row_x[-last_count:])),
                first_slope,
                last_slope,
            ))

        # For every fragment, find the most plausible continuation below it;
        # only reciprocal best matches are joined, which helps keep parallel
        # contour lines separate.
        next_match: dict[int, tuple[int, float]] = {}
        previous_match: dict[int, tuple[int, float]] = {}
        for first, (_first_top, first_bottom, _first_x_top, first_x_bottom, _first_slope_top, first_slope_bottom) in enumerate(bounds):
            best: tuple[int, float] | None = None
            for second, (second_top, _second_bottom, second_x_top, _second_x_bottom, second_slope_top, _second_slope_bottom) in enumerate(bounds):
                gap = second_top - first_bottom
                if gap <= 0 or gap > self.config["contours"]["stitch_max_gap_px"]:
                    continue
                predicted_x = first_x_bottom + first_slope_bottom * gap
                residual = abs(second_x_top - predicted_x)
                slope_delta = abs(first_slope_bottom - second_slope_top)
                # A contour can bend beneath an elevation label, so allow its
                # local tangent to change while still requiring the predicted
                # endpoint to remain closer than competing parallel lines.
                max_residual = max(
                    self.config["contours"]["stitch_residual_min_px"],
                    gap * self.config["contours"]["stitch_residual_gap_ratio"]
                    + self.config["contours"]["stitch_residual_extra_px"],
                )
                if residual > max_residual or slope_delta > self.config["contours"]["stitch_max_slope_delta"]:
                    continue
                score = (
                    residual
                    + slope_delta * self.config["contours"]["stitch_slope_weight"]
                    + gap * self.config["contours"]["stitch_gap_weight"]
                )
                if best is None or score < best[1]:
                    best = (second, score)
                candidate = (first, score)
                if second not in previous_match or score < previous_match[second][1]:
                    previous_match[second] = candidate
            if best is not None:
                next_match[first] = best

        for first, (second, score) in next_match.items():
            reverse = previous_match.get(second)
            if reverse is not None and reverse[0] == first and reverse[1] == score:
                union(first, second)

        groups: dict[int, list[int]] = {}
        for index in range(count):
            groups.setdefault(find(index), []).append(index)
        joined: list[tuple[np.ndarray, np.ndarray]] = []
        for indices in groups.values():
            ys = np.concatenate([fragments[i][0] for i in indices])
            xs = np.concatenate([fragments[i][1] for i in indices])
            joined.append((ys, xs))
        joined.sort(key=lambda line: (float(np.median(line[1])), float(np.median(line[0]))))
        return joined

    def _contour_color_mask(self, rgb: np.ndarray) -> np.ndarray:
        """Match the chosen hue while allowing antialiased changes in brightness."""
        normalized = np.asarray(rgb, dtype=np.float32) / 255.0
        target = np.asarray(self.contour_color, dtype=np.float32).reshape(1, 1, 3) / 255.0
        image_hsv = rgb_to_hsv(normalized)
        target_hsv = rgb_to_hsv(target)[0, 0]
        hue_delta = np.abs(image_hsv[..., 0] - target_hsv[0])
        hue_delta = np.minimum(hue_delta, 1.0 - hue_delta)
        tolerance = self.contour_tolerance.get()
        hue_tolerance = float(np.clip(
            tolerance / 255.0 * self.config["contours"]["hue_tolerance_scale"],
            self.config["contours"]["hue_tolerance_min"],
            self.config["contours"]["hue_tolerance_max"],
        ))
        minimum_saturation = max(
            self.config["contours"]["minimum_saturation_floor"],
            float(target_hsv[1]) * self.config["contours"]["minimum_saturation_target_fraction"],
        )
        return (hue_delta <= hue_tolerance) & (image_hsv[..., 1] >= minimum_saturation) & (image_hsv[..., 2] >= 0.12)

    def _update_manual_controls(self) -> None:
        count = len(self.contour_components)
        active = count > 0
        self.contour_counter.configure(text=f"{self.selected_contour_index + 1} / {count}" if active else "0 / 0")
        state = "normal" if active else "disabled"
        self.previous_contour_button.configure(state=state)
        self.next_contour_button.configure(state=state)
        self.manual_value_entry.configure(state=state)
        self.manual_status.configure(text=("Unassigned; interpolated from neighboring lines" if active and self.selected_contour_index + 1 not in self.manual_contour_values else ("Altitude assigned" if active else "Choose a contour color to detect lines")))
        self._updating_manual_value = True
        value = self.manual_contour_values.get(self.selected_contour_index + 1)
        self.manual_value_var.set("" if value is None else f"{value:g}")
        self._updating_manual_value = False

    def _previous_contour(self) -> None:
        if self.contour_components:
            self.selected_contour_index = (self.selected_contour_index - 1) % len(self.contour_components)
            self._update_manual_controls()
            if self.image is not None:
                self._render_surface()

    def _next_contour(self) -> None:
        if self.contour_components:
            self.selected_contour_index = (self.selected_contour_index + 1) % len(self.contour_components)
            self._update_manual_controls()
            if self.image is not None:
                self._render_surface()

    def _manual_value_changed(self, *_args: object) -> None:
        if self._updating_manual_value or not self.contour_components:
            return
        key = self.selected_contour_index + 1
        text = self.manual_value_var.get().strip().replace(",", ".")
        if not text:
            self.manual_contour_values.pop(key, None)
        else:
            try:
                value = float(text)
                if not np.isfinite(value):
                    return
                self.manual_contour_values[key] = value
                if self.elevation.get() == 0:
                    self.elevation.set(1.0)
                    self.value_label.configure(text="1.00×")
            except ValueError:
                return
        self.contour_counter.configure(text=f"{self.selected_contour_index + 1} / {len(self.contour_components)}" if self.contour_components else "0 / 0")
        self.manual_status.configure(text=("Unassigned; interpolated from neighboring lines" if self.contour_components and self.selected_contour_index + 1 not in self.manual_contour_values else ("Altitude assigned" if self.contour_components else "Choose a contour color to detect lines")))
        if self.image is not None:
            self._render_surface()

    def _interpolate_manual_contours(self, shape: tuple[int, int]) -> np.ndarray | None:
        if not self.contour_components or not self.manual_contour_values:
            return None
        height, width = shape
        count = len(self.contour_components)
        known_indices = np.asarray(sorted(self.manual_contour_values), dtype=np.float32)
        known_values = np.asarray([self.manual_contour_values[int(i)] for i in known_indices], dtype=np.float32)
        line_values = np.interp(np.arange(1, count + 1), known_indices, known_values)
        positions = np.empty((count, height), dtype=np.float32)
        source_height, source_width = self.color_image.size[1], self.color_image.size[0]
        for i, (source_ys, source_xs) in enumerate(self.contour_components):
            ys = np.rint(source_ys * (height - 1) / max(1, source_height - 1)).astype(np.int32)
            xs = np.rint(source_xs * (width - 1) / max(1, source_width - 1)).astype(np.int32)
            unique_y = np.unique(ys)
            median_x = np.asarray([np.median(xs[ys == row]) for row in unique_y], dtype=np.float32)
            positions[i] = np.interp(np.arange(height), unique_y, median_x)
        surface = np.zeros((height, width), dtype=np.float32)
        x_coords = np.arange(width, dtype=np.float32)
        for row in range(height):
            order = np.argsort(positions[:, row])
            anchors_x = positions[order, row]
            anchors_z = line_values[order]
            unique_x, inverse = np.unique(np.round(anchors_x, 1), return_inverse=True)
            if len(unique_x) < 2:
                surface[row, :] = float(anchors_z[0])
                continue
            sums = np.bincount(inverse, weights=anchors_z)
            counts = np.bincount(inverse)
            surface[row] = np.interp(x_coords, unique_x, sums / counts)
        low, high = float(np.min(line_values)), float(np.max(line_values))
        if high > low:
            surface = (surface - low) / (high - low)
        else:
            surface.fill(0.5)
        return ndimage.gaussian_filter(surface, sigma=(0.8, 0.5)).astype(np.float32)

    @staticmethod
    def _distance_from_lines(mask: np.ndarray) -> np.ndarray:
        """Approximate Euclidean distance to selected pixels with a chamfer pass."""
        h, w = mask.shape
        distance = np.where(mask, 0.0, float(h + w)).astype(np.float32)
        diagonal = np.float32(1.41421356)
        for y in range(h):
            for x in range(w):
                if y:
                    distance[y, x] = min(distance[y, x], distance[y - 1, x] + 1)
                    if x:
                        distance[y, x] = min(distance[y, x], distance[y - 1, x - 1] + diagonal)
                    if x + 1 < w:
                        distance[y, x] = min(distance[y, x], distance[y - 1, x + 1] + diagonal)
                if x:
                    distance[y, x] = min(distance[y, x], distance[y, x - 1] + 1)
        for y in range(h - 1, -1, -1):
            for x in range(w - 1, -1, -1):
                if y + 1 < h:
                    distance[y, x] = min(distance[y, x], distance[y + 1, x] + 1)
                    if x:
                        distance[y, x] = min(distance[y, x], distance[y + 1, x - 1] + diagonal)
                    if x + 1 < w:
                        distance[y, x] = min(distance[y, x], distance[y + 1, x + 1] + diagonal)
                if x + 1 < w:
                    distance[y, x] = min(distance[y, x], distance[y, x + 1] + 1)
        return distance

    def _slider_changed(self, _value: str) -> None:
        value = self.elevation.get()
        self.value_label.configure(text=f"{value:.2f}×")
        if self.image is not None:
            self._render_surface()

    def _invert_changed(self) -> None:
        if self.image is not None:
            self._render_surface()

    def _draw_empty(self) -> None:
        self.ax.clear()
        self._apply_plot_background()
        text_color = "#ffffff" if self.black_background.get() else "#526174"
        self.ax.text2D(0.5, 0.53, "Choose an image to create a 3D relief", transform=self.ax.transAxes, ha="center", color=text_color, fontsize=14)
        self.ax.set_axis_off()
        self.canvas.draw_idle()

    def _render_surface(self) -> None:
        assert self.image is not None
        im = self.image.copy()
        im.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
        manual_surface = None
        if self.contour_color is not None and self.manual_contour_values:
            # Map manually supplied line elevations continuously between curves.
            rgb_small = self.color_image.copy()
            rgb_small.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
            manual_surface = self._interpolate_manual_contours(np.asarray(rgb_small).shape[:2])
        if manual_surface is not None:
            pixels = manual_surface
        elif self.contour_color is None:
            # Preserve the original brightness-based behavior unless a color is selected.
            smooth_height = im.filter(ImageFilter.GaussianBlur(self.HEIGHT_SMOOTHING))
            pixels = np.asarray(smooth_height, dtype=np.float32) / 255.0
        else:
            assert self.color_image is not None
            rgb_small = self.color_image.copy()
            rgb_small.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
            rgb_array = np.asarray(rgb_small, dtype=np.float32)
            selected = self._contour_color_mask(rgb_array)
            if not selected.any():
                messagebox.showwarning("No contour pixels found", "Try a higher color tolerance or choose a color present in the image.", parent=self.root)
                return
            distances = self._distance_from_lines(selected)
            distance_scale = max(1.0, float(np.percentile(distances, 95)))
            distance_image = Image.fromarray(np.clip(distances / distance_scale * 255, 0, 255).astype(np.uint8))
            smooth_height = distance_image.filter(ImageFilter.GaussianBlur(self.HEIGHT_SMOOTHING))
            pixels = np.asarray(smooth_height, dtype=np.float32) / 255.0
        # Keep the map's original colours on the mesh; luminance drives height.
        assert self.color_image is not None
        rgb = self.color_image.copy()
        rgb.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
        colors = np.asarray(rgb, dtype=np.float32) / 255.0
        height, width = pixels.shape
        x = np.linspace(0, width - 1, width)
        y = np.linspace(height - 1, 0, height)
        X, Y = np.meshgrid(x, y)
        # The slider controls vertical exaggeration relative to the map size.
        height_map = 1.0 - pixels if self.invert_elevation.get() else pixels
        # Keep the image-size based relief scale, then calibrate it by the
        # supplied contour interval (the same multiplier works in either mode).
        if manual_surface is not None:
            vertical_unit = max(self.manual_contour_values.values()) - min(self.manual_contour_values.values())
            vertical_unit = vertical_unit or 1.0
        else:
            vertical_unit = self.contour_interval or 1.0
        Z = height_map * self.elevation.get() * min(width, height) * 0.02 * vertical_unit
        # plot_surface assigns one colour to each quad, so average its corners.
        facecolors = (colors[:-1, :-1] + colors[1:, :-1] + colors[:-1, 1:] + colors[1:, 1:]) / 4
        if self.contour_components:
            # Highlight the active detected contour in vivid pink on the mesh.
            source_ys, source_xs = self.contour_components[self.selected_contour_index]
            source_height, source_width = self.color_image.size[1], self.color_image.size[0]
            line_mask = np.zeros((height, width), dtype=bool)
            scaled_y = np.rint(source_ys * (height - 1) / max(1, source_height - 1)).astype(np.int32)
            scaled_x = np.rint(source_xs * (width - 1) / max(1, source_width - 1)).astype(np.int32)
            line_mask[scaled_y, scaled_x] = True
            selected_faces = (
                line_mask[:-1, :-1]
                | line_mask[1:, :-1]
                | line_mask[:-1, 1:]
                | line_mask[1:, 1:]
            )
            facecolors[selected_faces] = (1.0, 0.0, 0.72)
        self.ax.clear()
        self._apply_plot_background()
        self.ax.plot_surface(X, Y, Z, facecolors=facecolors, rstride=1, cstride=1, linewidth=0, antialiased=True, shade=False)
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Elevation")
        self.ax.set_title(Path(self.filename).name, pad=14, fontsize=10)
        # Keep the axes proportional to the data ranges; mismatched ranges
        # make small pixel variations look like tall spikes.
        vertical_scale = max(1.0, float(np.ptp(Z)))
        self.ax.set_box_aspect((width, height, vertical_scale))
        self.ax.view_init(elev=32, azim=-55)
        self.ax.grid(False)
        self.canvas.draw_idle()


def main() -> None:
    root = tk.Tk()
    ReliefApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
