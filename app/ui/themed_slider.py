"""Canvas-drawn slider: thin track, accent-coloured fill and a round knob (replaces tk.Scale)."""
import tkinter as tk


class ThemedSlider(tk.Canvas):
    def __init__(self, parent, from_, to, variable, command=None, length=160, bg="#1e1e1e",
                 track="#444444", accent="#ff8c00", knob="#cfcfcf", knob_outline="#101010",
                 disabled="#666666", fg="#ffffff", font=None, show_value=True, fill_from_center=False,
                 scale=1.0):
        self._lo, self._hi = from_, to
        self._var = variable
        self._command = command
        self._len = int(length)
        self._show_value = show_value
        self._center = fill_from_center
        self._enabled = True
        self._pad = int(10 * scale)
        self._r = int(8 * scale)
        self._track_h = max(3, int(4 * scale))
        self._text_h = int(16 * scale) if show_value else 0
        self._colors = dict(track=track, accent=accent, knob=knob, outline=knob_outline,
                            disabled=disabled, fg=fg)
        self._font = font
        height = self._text_h + 2 * self._r + int(4 * scale)
        super().__init__(parent, width=self._len, height=height, bg=bg, highlightthickness=0, bd=0)
        self._cy = self._text_h + self._r + int(2 * scale)
        self._trace = variable.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self._on_mouse)
        self.bind("<B1-Motion>", self._on_mouse)
        self.bind("<Destroy>", self._on_destroy)
        self._draw()

    def _on_destroy(self, event):
        if event.widget is self:
            try:
                self._var.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass

    def _value(self):
        try:
            return max(self._lo, min(self._hi, int(self._var.get())))
        except (tk.TclError, ValueError):
            return self._lo

    def _x_for(self, value):
        span = max(1, self._hi - self._lo)
        return self._pad + (value - self._lo) / span * (self._len - 2 * self._pad)

    def _draw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        c = self._colors
        v = self._value()
        x = self._x_for(v)
        left, right = self._pad, self._len - self._pad
        half = self._track_h / 2
        accent = c["accent"] if self._enabled else c["disabled"]
        self.create_rectangle(left, self._cy - half, right, self._cy + half, fill=c["track"], outline="")
        start = self._x_for(0) if self._center else left
        self.create_rectangle(min(start, x), self._cy - half, max(start, x), self._cy + half,
                              fill=accent, outline="")
        self.create_oval(x - self._r, self._cy - self._r, x + self._r, self._cy + self._r,
                         fill=c["knob"] if self._enabled else c["disabled"], outline=c["outline"], width=2)
        if self._show_value:
            self.create_text(x, self._text_h / 2, text=str(v), fill=c["fg"] if self._enabled else c["disabled"],
                             font=self._font)

    def _on_mouse(self, event):
        if not self._enabled:
            return
        usable = max(1, self._len - 2 * self._pad)
        ratio = max(0.0, min(1.0, (event.x - self._pad) / usable))
        value = int(round(self._lo + ratio * (self._hi - self._lo)))
        if value != self._value():
            self._var.set(value)
            if self._command:
                self._command(value)

    def get(self):
        return self._value()

    def set(self, value):
        self._var.set(value)

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self._draw()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure


def slider_colors(theme):
    orange = theme in ("elite_orange", "modern_orange")
    return dict(track="#3a3a3a" if orange else "#555555", accent="#ff8c00" if orange else "#4a9eff")
