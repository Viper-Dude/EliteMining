# -*- coding: utf-8 -*-
"""Widgets used only by the Modern theme."""
from ui.theme import modern_color
import tkinter as tk
from tkinter import ttk, font as tkfont

from config import load_theme
from ui.theme import get_theme_colors


class RoundedButton(tk.Canvas):
    """Flat button with rounded corners. Supports configure(text=/state=/command=) like tk.Button."""

    def __init__(self, parent, text="", command=None, primary=False, font=None,
                 radius=6, padx=12, pady=4, **_ignored):
        self._c = get_theme_colors(load_theme())
        self._text = text
        self._command = command
        self._primary = primary
        self._radius = radius
        self._padx = padx
        self._pady = pady
        self._state = "normal"
        self._hover = False
        self._pressed = False
        self._font = tkfont.Font(font=font) if font else tkfont.Font(family="Segoe UI", size=9)
        super().__init__(parent, bg=self._parent_bg(parent), highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self._focused = False
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<space>", self._on_space)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._redraw()

    def _parent_bg(self, parent):
        try:
            return parent.cget("bg")
        except tk.TclError:
            try:
                return ttk.Style(parent).lookup(parent.winfo_class(), "background") or self._c["bg"]
            except tk.TclError:
                return self._c["bg"]

    def _set_hover(self, value):
        self._hover = value
        self._redraw()

    def _set_focus(self, value):
        self._focused = value
        self._redraw()

    def _on_space(self, _e):
        if self._state == "normal" and self._command:
            self._command()
        return "break"

    def _on_press(self, _e):
        if self._state == "normal":
            self._pressed = True
            self._redraw()

    def _on_release(self, e):
        was_pressed, self._pressed = self._pressed, False
        self._redraw()
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was_pressed and inside and self._command:
            self._command()

    def _colors(self):
        c = self._c
        if self._state == "disabled":
            return c["btn_bg_disabled"], c["btn_fg_disabled"], c["border"]
        if self._primary:
            fill = modern_color("#E88A28") if self._pressed else (modern_color("#FFB05A") if self._hover else c["accent"])
            return fill, c["accent_fg"], fill
        fill = c["btn_bg_hover"] if self._hover else c["btn_bg"]
        return fill, c["fg"], c["accent"] if self._hover else c["border"]

    def _redraw(self):
        self.delete("all")
        w = max(self._font.measure(self._text) + 2 * self._padx, getattr(self, "_min_w", 0))
        h = self._font.metrics("linespace") + 2 * self._pady
        self.configure_canvas(width=w, height=h)
        fill, fg, outline = self._colors()
        r = self._radius
        x0, y0, x1, y1 = 1, 1, w - 1, h - 1
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        if self._focused and self._state == "normal":
            outline = self._c["fg"] if self._primary else self._c["accent"]
        self.create_polygon(pts, smooth=True, fill=fill, outline=outline)
        self.create_text(w // 2, h // 2, text=self._text, fill=fg, font=self._font)

    def configure_canvas(self, **kw):
        tk.Canvas.configure(self, **kw)

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        redraw = False
        for key in ("text", "command", "state", "font"):
            if key in kw:
                value = kw.pop(key)
                if key == "text":
                    self._text = value
                elif key == "command":
                    self._command = value
                elif key == "state":
                    self._state = value
                    tk.Canvas.configure(self, cursor="hand2" if value == "normal" else "arrow")
                elif key == "font":
                    self._font = tkfont.Font(font=value)
                redraw = True
        for key in ("bg", "fg", "activebackground", "activeforeground", "relief", "bd", "padx", "pady",
                    "highlightbackground", "highlightcolor"):
            kw.pop(key, None)
        if kw:
            tk.Canvas.configure(self, **kw)
        if redraw:
            self._redraw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return tk.Canvas.cget(self, key)


class RoundedProgressBar(tk.Canvas):
    """Pill-shaped progress bar. Set progress with bar['value'] = 0..100."""

    def __init__(self, parent, height=10, **_ignored):
        self._c = get_theme_colors(load_theme())
        self._value = 0.0
        try:
            bg = parent.cget("bg")
        except tk.TclError:
            bg = ttk.Style(parent).lookup(parent.winfo_class(), "background") or self._c["bg"]
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._redraw())

    def _pill(self, x0, x1, fill):
        h = int(self.cget("height"))
        r = h / 2
        if x1 - x0 < h:
            self.create_oval(x0, 0, x0 + h, h, fill=fill, outline=fill)
            return
        self.create_oval(x0, 0, x0 + h, h, fill=fill, outline=fill)
        self.create_oval(x1 - h, 0, x1, h, fill=fill, outline=fill)
        self.create_rectangle(x0 + r, 0, x1 - r, h, fill=fill, outline=fill)

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            return
        self._pill(0, w, modern_color("#2A3038"))
        if self._value > 0:
            self._pill(0, max(int(self.cget("height")), int(w * self._value / 100)), self._c["accent"])

    def __setitem__(self, key, value):
        if key == "value":
            self._value = max(0.0, min(100.0, float(value)))
            self._redraw()
        else:
            tk.Canvas.__setitem__(self, key, value)

    def __getitem__(self, key):
        return self._value if key == "value" else tk.Canvas.__getitem__(self, key)


def make_pill_image(fill, outline, size=24, radius=6, scale=4):
    """9-slice rounded rectangle (transparent corners) for ttk image elements."""
    from PIL import Image, ImageDraw, ImageTk

    def rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    big = size * scale
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * scale, fill=255)
    inner = Image.new("L", (big, big), 0)
    ImageDraw.Draw(inner).rounded_rectangle((scale, scale, big - 1 - scale, big - 1 - scale),
                                            radius=radius * scale - scale, fill=255)
    img = Image.new("RGBA", (big, big), rgb(outline) + (255,))
    img.paste(rgb(fill) + (255,), mask=inner)
    img.putalpha(mask)
    return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))


_NEUTRAL_FILLS = {"#333333", "#2a2a2a", "#3a3a3a", "#1a1a1a", "#444444", "#2d2d2d", "#252525", "#1e1e1e",
                  "#2a3a4a", "#4a3a2a", "#3a4a5a", "#404040", "#555555", "#2e2e2e", "#222222", "#000000",
                  "#0a0a0a", "#3d3d3d", "#353535", "#14171b", "#1d2228", "#262c34", modern_color("#14171b").lower(), modern_color("#1d2228").lower(), modern_color("#262c34").lower(), "#4a4a4a"}


def _blend(c1, c2, t):
    a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# Primary-action labels (letters only, lowercase): EN + DE
_SEARCH_WORDS = {"search", "suchen", "calculatedistance", "entfernungberechnen"}


def _letters(text):
    return "".join(ch for ch in str(text) if ch.isalpha()).lower()


def _is_search_label(text):
    return _letters(text) in _SEARCH_WORDS


def _is_green(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return g > r + 15 and g > b + 15


# Green stays only for positive/confirm actions; any other green helper button turns neutral.
_KEEP_GREEN = {"start", "save", "ok", "gotit", "selectall", "addbookmark", "applytosession"}


class ModernButton(RoundedButton):
    """Drop-in for tk.Button in the Modern theme: rounded, keeps semantic fill colors (green/red/...),
    neutral grays become the Modern button color. Unsupported tk.Button options are ignored."""

    def __init__(self, parent, text="", command=None, font=None, bg=None, fg=None, width=None,
                 padx=None, pady=None, state="normal", cursor=None, **_ignored):
        self._fill = None
        self._fg_override = None
        self._set_colors(bg, fg)
        super().__init__(parent, text=text, command=command, font=font,
                         padx=max(8, int(padx)) if padx else 12, pady=max(3, int(pady)) if pady else 4)
        if width:
            self._min_w = int(width) * self._font.measure("0")
        self._state = state if state in ("normal", "disabled") else "normal"
        self._apply_search_style()

    def _apply_search_style(self):
        """Search buttons are the primary action: orange fill + bold, like the Hotspots Finder one."""
        if self._fill and _is_green(self._fill) and _letters(self._text) not in _KEEP_GREEN:
            self._fill = None
        primary = _is_search_label(self._text)
        if primary:
            # No emoji on the primary button: drop any leading symbols/spaces from the label
            self._text = self._text.lstrip("".join(ch for ch in self._text if not ch.isalnum())).strip()
        if primary != self._primary or (primary and not self._font.actual("weight") == "bold"):
            self._primary = primary
            self._font.configure(weight="bold" if primary else "normal")
        self._redraw()

    # Bright legacy accent colors softened to sit with the Modern palette ("" = use the neutral button color)
    _SOFTEN = {"#4a9eff": "#3B6EA8", "#ff6b6b": "#B04A4A", "#4caf50": "#2E7D4F", "#666666": ""}

    def _set_colors(self, bg, fg):
        if bg is not None:
            b = str(bg).lower()
            b = self._SOFTEN.get(b, b)
            if b == "":
                self._fill = None
                b = None
        if bg is not None and b is not None:
            self._fill = None if (b in _NEUTRAL_FILLS or not b.startswith("#") or len(b) != 7) else b
        if fg is not None and str(fg).startswith("#") and len(str(fg)) == 7:
            self._fg_override = str(fg)

    def _colors(self):
        c = self._c
        if self._primary:
            return RoundedButton._colors(self)
        if self._fill:
            if self._state == "disabled":
                f = _blend(self._fill, c["bg"], 0.55)
                return f, c["btn_fg_disabled"], f
            f = _blend(self._fill, "#FFFFFF", 0.15) if self._hover else self._fill
            return f, "#FFFFFF", f
        fill, fg, outline = RoundedButton._colors(self)
        if self._fg_override and self._state != "disabled":
            fg = self._fg_override
        return fill, fg, outline

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        self._set_colors(kw.get("bg"), kw.get("fg"))
        allowed = {k: v for k, v in kw.items() if k in ("text", "command", "state", "font")}
        if "cursor" in kw:
            tk.Canvas.configure(self, cursor=kw["cursor"])
        RoundedButton.configure(self, **allowed)
        self._apply_search_style()

    config = configure

    def cget(self, key):
        if key in ("bg", "background"):
            return self._fill or self._c["btn_bg"]
        if key == "command":
            return self._command
        return RoundedButton.cget(self, key)

    def invoke(self):
        if self._state == "normal" and self._command:
            return self._command()

    def flash(self):
        pass


_OrigTkButton = tk.Button


def install_modern_buttons():
    """Make every tk.Button created from now on a ModernButton (image/textvariable buttons stay native)."""
    try:
        from localization import t
        for key in ("mining_session.start", "dialogs.save", "common.ok", "refinery_dialog.apply_to_session",
                    "dialogs.got_it", "settings.select_all", "bookmarks.add_bookmark"):
            _KEEP_GREEN.add(_letters(t(key)))
    except Exception:
        pass

    def factory(master=None, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if any(k in kw for k in ("image", "textvariable", "bitmap")):
            return _OrigTkButton(master, **kw)
        return ModernButton(master, **kw)
    tk.Button = factory
