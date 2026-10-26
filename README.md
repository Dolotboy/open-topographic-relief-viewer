# Image to 3D Relief

A small Python desktop app that turns an image into an interactive 3D surface. The image is displayed as a color texture, and its grayscale values define the terrain height. By default, light pixels rise and dark pixels sink. Use the **Invert elevation** checkbox to reverse this, and the elevation slider to control the relief strength.

## Run the app

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Click **Choose an image…** to load an image. Common formats are supported, including PNG, JPG/JPEG, WebP, BMP, TIFF, and GIF. Drag over the plot to rotate the view; use the mouse wheel to zoom.

The display resolution is reduced automatically to keep interaction smooth. The grayscale height field is smoothed to prevent thin contour lines from becoming sharp ridges.
