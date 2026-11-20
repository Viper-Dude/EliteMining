"""Anti-aliased circles for Canvas widgets (Tk canvas ovals have no smoothing)."""
from PIL import Image, ImageDraw, ImageTk

_SS = 6  # supersampling factor


def smooth_circle(canvas, diameter, fill=None, outline=None, outline_width=0):
    """PhotoImage of a circle; cached per Tk root so it survives widget redraws."""
    root = canvas._root()
    cache = root.__dict__.setdefault("_smooth_circle_images", {})
    key = (diameter, fill, outline, outline_width)
    if key in cache:
        return cache[key]
    size = int(diameter)
    s = size * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = int(outline_width * _SS)
    d.ellipse((0, 0, s - 1, s - 1), fill=outline if (outline and w) else fill)
    if outline and w:
        d.ellipse((w, w, s - 1 - w, s - 1 - w), fill=fill)
    photo = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS), master=root)
    cache[key] = photo
    return photo
