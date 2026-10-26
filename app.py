"""Turn an image into an interactive 3D relief surface."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
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
        self.elevation = tk.DoubleVar(value=0.0)
        self.invert_elevation = tk.BooleanVar(value=False)
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
        self.file_label = ttk.Label(outer, text="No image selected", foreground="#666")
        self.file_label.pack(anchor="w", pady=(0, 6))
        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor="#f5f7fa")
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.fig.subplots_adjust(left=0.02, right=0.98, bottom=0.03, top=0.96)
        self.canvas = FigureCanvasTkAgg(self.fig, master=outer)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        ttk.Label(outer, text="Tip: drag the mouse over the surface to rotate it.", foreground="#666").pack(anchor="w", pady=(8, 0))

    def open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif"), ("All files", "*.*")],
        )
        if not path:
            return
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
            # Every newly loaded map starts as a flat, textured plane.
            self.elevation.set(0.0)
            self.value_label.configure(text="0.00×")
            self.file_label.configure(text=f"{Path(path).name}  ·  {self.image.width} × {self.image.height} px")
            self._render_surface()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open image", str(exc), parent=self.root)

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
        self.ax.set_facecolor("#f5f7fa")
        self.ax.text2D(0.5, 0.53, "Choose an image to create a 3D relief", transform=self.ax.transAxes, ha="center", color="#526174", fontsize=14)
        self.ax.set_axis_off()
        self.canvas.draw_idle()

    def _render_surface(self) -> None:
        assert self.image is not None
        im = self.image.copy()
        im.thumbnail((self.MAX_SIDE, self.MAX_SIDE), Image.Resampling.LANCZOS)
        # Contour strokes are sharp and narrow; blur the height field so they
        # blend into the surrounding terrain instead of becoming raised ridges.
        smooth_height = im.filter(ImageFilter.GaussianBlur(self.HEIGHT_SMOOTHING))
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
        Z = height_map * self.elevation.get() * min(width, height) * 0.02
        # plot_surface assigns one colour to each quad, so average its corners.
        facecolors = (colors[:-1, :-1] + colors[1:, :-1] + colors[:-1, 1:] + colors[1:, 1:]) / 4
        self.ax.clear()
        self.ax.set_facecolor("#f5f7fa")
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
