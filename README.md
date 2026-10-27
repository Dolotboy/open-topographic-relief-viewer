# Image to 3D Relief

A small Python desktop app that turns an image into an interactive 3D surface. By default, the image's grayscale brightness defines terrain height: light pixels rise and dark pixels sink. Use **Invert elevation** to reverse this and the elevation slider to control relief strength.

## Run the app

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Click **Choose an image…** to load a PNG, JPG/JPEG, WebP, BMP, TIFF, or GIF. The app asks for the vertical contour interval in meters: enter the elevation difference between adjacent contour lines (for example, `1` or `5`), or leave it blank when unknown. The interval scales the displayed relief in either detection mode.

## Topography detection

By default, the app converts the complete image to grayscale, smooths it with a Gaussian blur, and uses brightness as the height field. Roads, map borders, labels, and other screenshot graphics can therefore affect the relief.

For maps with colored contour lines, choose **Pick from image…** and click a contour on the original image, or use **Choose contour color…** to select a color manually. **Color tolerance** controls how far a pixel's hue may differ from the chosen color. The matcher allows brightness variation from antialiasing, so pale edge pixels can still belong to a contour. Raise the tolerance to include more color variation; lower it to exclude nearby hues. The app makes a mask of matching pixels, estimates every pixel's distance to the nearest selected line, normalizes those distances into a continuous height field, and blurs the result to soften screenshot artifacts. The original image remains the surface texture, and **Invert elevation** also applies to this field.

After choosing a contour color, the app links nearby contour fragments when their endpoint direction and position indicate a continuation, then the **Manual contour altitude** controls let you move through detected lines from left to right. If a contour interval was supplied, the lines are prefilled with successive altitudes starting at one interval (for example, 1, 2, 3 m for a 1 m interval, or 5, 10, 15 m for a 5 m interval). You can edit or clear any value. The active line is highlighted in vivid pink on the 3D surface. Lines without a value are assigned interpolated heights between the entered references, and the 3D surface updates as you type. These manual altitudes take precedence over proximity-based height estimation.

The interval prompt accepts a positive number or a blank value. A supplied interval scales the vertical relief in meters in either mode; the elevation slider remains a vertical exaggeration control. Supplying an interval starts the elevation slider at `1×` so the interval is visible immediately. Leaving the interval blank uses relative scale and preserves the flat-on-load behavior. Distance alone cannot determine whether terrain rises or falls across a contour, recover absolute elevations, or interpret contour labels. This method produces an approximate proximity-based relief rather than a surveyed elevation model.

The display resolution is reduced automatically to keep interaction smooth. Drag over the plot to rotate the view; scroll up to zoom in and down to zoom out.

## Configuration

Edit `config.json` beside `app.py` and restart the app to apply changes. Colors use CSS hex notation. `elevation.slider_max` sets the elevation slider's maximum. Under `contours`, `color_tolerance` is the starting slider value and `color_tolerance_max` its maximum; setting the slider to zero now means exact hue matching. `minimum_component_pixels` filters tiny pixel clusters, while `minimum_contour_span_fraction` discards detections shorter than that fraction of the image's longest dimension. Lower this fraction to keep shorter real contours; raise it to reject more isolated fragments. `closing_size` joins very small pixel gaps. The `stitch_*` settings control how far apart contour fragments may be, how much their predicted position and direction may differ, and how candidates are ranked. `hue_tolerance_*` and `minimum_saturation_*` tune color matching. `display.max_side` and `display.height_smoothing` adjust mesh resolution and smoothing.

To combine more broken pieces into one contour, increase `stitch_max_gap_px`, `stitch_residual_gap_ratio`, `stitch_residual_extra_px`, and `stitch_max_slope_delta`. This reduces the line count but can merge neighboring contours if set too high. `stitch_slope_weight` and `stitch_gap_weight` rank eligible matches; lowering them makes slope and gap length matter less than endpoint proximity. These stitching settings are separate from the color-tolerance slider.

## Demo
- Demo-5.png: Black background, select color : 214,120,53
