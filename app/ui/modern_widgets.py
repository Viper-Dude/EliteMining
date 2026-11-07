# -*- coding: utf-8 -*-
"""Widgets used only by the Modern theme."""
import tkinter as tk
from tkinter import ttk, font as tkfont

from ui.theme import get_theme_colors


class RoundedButton(tk.Canvas):
    """Flat button with rounded corners. Supports configure(text=/state=/command=) like tk.Button."""

    def __init__(self, parent, text="", command=None, primary=False, font=None,
                 radius=6, padx=12, pady=4, **_ignored):
        self._c = get_theme_colors("modern")
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
        super().__init__(parent, bg=self._parent_bg(parent), highlightthickness=0, bd=0, cursor="hand2")
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
            fill = "#E88A28" if self._pressed else ("#FFB05A" if self._hover else c["accent"])
            return fill, c["accent_fg"], fill
        fill = c["btn_bg_hover"] if self._hover else c["btn_bg"]
        return fill, c["fg"], c["accent"] if self._hover else c["border"]

    def _redraw(self):
        self.delete("all")
        w = self._font.measure(self._text) + 2 * self._padx
        h = self._font.metrics("linespace") + 2 * self._pady
        self.configure_canvas(width=w, height=h)
        fill, fg, outline = self._colors()
        r = self._radius
        x0, y0, x1, y1 = 1, 1, w - 1, h - 1
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
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
        self._c = get_theme_colors("modern")
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
        self._pill(0, w, "#2A3038")
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
