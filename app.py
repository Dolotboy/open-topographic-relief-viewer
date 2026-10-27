"""Turn an image into an interactive 3D relief surface."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class ReliefApp:
    MAX_SIDE = 220
    HEIGHT_SMOOTHING = 5.0

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
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
        self.contour_tolerance = tk.IntVar(value=35)
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
        self.slider = ttk.Scale(controls, from_=0, to=100, variable=self.elevation, command=self._slider_changed)
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
        ttk.Label(contour, text="Color tolerance").pack(side="left", padx=(12, 4))
        self.tolerance_slider = ttk.Scale(contour, from_=0, to=150, variable=self.contour_tolerance, command=self._tolerance_changed)
        self.tolerance_slider.pack(side="left", fill="x", expand=True, padx=4)
        self.tolerance_label = ttk.Label(contour, text="35", width=4, anchor="e")
        self.tolerance_label.pack(side="left")
        self.contour_label = ttk.Label(contour, text="No color selected; using image brightness")
        self.contour_label.pack(anchor="w", pady=(5, 0))
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
        background = "#000000" if self.black_background.get() else "#f5f7fa"
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
            # A supplied contour interval should have a visible effect on load.
            # Blank intervals retain the original flat-on-load behavior.
            initial_elevation = 1.0 if self.contour_interval is not None else 0.0
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
        self.contour_color = tuple(int(round(channel)) for channel in result[0])
        self.contour_button.configure(text=f"Contour color: {result[1]}")
        self.contour_label.configure(text="Selected pixels define the contour distance field")
        if self.image is not None:
            self._render_surface()

    def _tolerance_changed(self, _value: str) -> None:
        tolerance = int(round(self.contour_tolerance.get()))
        self.contour_tolerance.set(tolerance)
        self.tolerance_label.configure(text=str(tolerance))
        if self.image is not None and self.contour_color is not None:
            self._render_surface()

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
        if self.contour_color is None:
            # Preserve the original brightness-based behavior unless a color is selected.
            smooth_height = im.filter(ImageFilter.GaussianBlur(self.HEIGHT_SMOOTHING))
            pixels = np.asarray(smooth_height, dtype=np.float32) / 255.0
        else:
            assert self.color_image is not None
            rgb_small = self.color_image.copy()
            rgb_small.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
            rgb_array = np.asarray(rgb_small, dtype=np.int16)
            target = np.asarray(self.contour_color, dtype=np.int16)
            delta = rgb_array - target
            selected = np.sum(delta * delta, axis=2) <= self.contour_tolerance.get() ** 2
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
        vertical_unit = self.contour_interval or 1.0
        Z = height_map * self.elevation.get() * min(width, height) * 0.02 * vertical_unit
        # plot_surface assigns one colour to each quad, so average its corners.
        facecolors = (colors[:-1, :-1] + colors[1:, :-1] + colors[:-1, 1:] + colors[1:, 1:]) / 4
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
