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

For maps with colored contour lines, choose **Choose contour color…** and select the line color. **Color tolerance** controls how far a pixel's RGB color may differ from the chosen color. Raise it to include antialiased or compressed line pixels; lower it to exclude nearby colors. The app makes a mask of matching pixels, estimates every pixel's distance to the nearest selected line, normalizes those distances into a continuous height field, and blurs the result to soften screenshot artifacts. The original image remains the surface texture, and **Invert elevation** also applies to this field.

The interval prompt accepts a positive number or a blank value. A supplied interval scales the vertical relief in meters in either mode; the elevation slider remains a vertical exaggeration control. Supplying an interval starts the elevation slider at `1×` so the interval is visible immediately. Leaving the interval blank uses relative scale and preserves the flat-on-load behavior. Distance alone cannot determine whether terrain rises or falls across a contour, recover absolute elevations, or interpret contour labels. This method produces an approximate proximity-based relief rather than a surveyed elevation model.

The display resolution is reduced automatically to keep interaction smooth. Drag over the plot to rotate the view; scroll up to zoom in and down to zoom out.
