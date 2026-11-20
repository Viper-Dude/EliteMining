"""Row of round colour swatches with the selected colour's name beside it (replaces an OptionMenu)."""
import tkinter as tk
import tkinter.font as tkfont

from ui.smooth_shapes import smooth_circle


class ColorSwatchPicker(tk.Canvas):
    def __init__(self, parent, options, variable, names=None, bg="#1e1e1e", ring="#ff8c00",
                 fg="#ffffff", disabled="#666666", font=None, scale=1.0):
        self._swatches = options
        self._var = variable
        self._names = names or {}
        self._enabled = True
        self._font = font
        self._colors = dict(ring=ring, fg=fg, disabled=disabled, outline="#101010")
        self._d = int(15 * scale)
        self._gap = int(6 * scale)
        self._pad = int(4 * scale)
        self._ring_w = max(2, int(2 * scale))
        n = len(options)
        swatches_w = self._pad * 2 + n * self._d + (n - 1) * self._gap
        try:
            measure = tkfont.Font(font=font).measure if font else (lambda s: 80)
            text_w = max(measure(self._names.get(k, k)) for k in options)
        except tk.TclError:
            text_w = int(90 * scale)
        self._text_x = swatches_w + int(8 * scale)
        height = self._d + 2 * self._pad + 2 * self._ring_w
        super().__init__(parent, width=self._text_x + text_w + self._pad, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._cy = height // 2
        self._trace = variable.trace_add("write", lambda *_: self.refresh())
        self.bind("<Button-1>", self._on_click)
        self.bind("<Destroy>", self._on_destroy)
        self.refresh()

    def _on_destroy(self, event):
        if event.widget is self:
            try:
                self._var.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass

    def _x0(self, index):
        return self._pad + self._ring_w + index * (self._d + self._gap)

    def refresh(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        c = self._colors
        current = self._var.get()
        r = self._d / 2
        for i, (key, hexcol) in enumerate(self._swatches.items()):
            x0 = self._x0(i)
            cx = x0 + r
            if key == current:
                ring = smooth_circle(self, int(self._d + 2 * (self._ring_w + 1)), fill=self.cget("bg"),
                                     outline=c["ring"] if self._enabled else c["disabled"],
                                     outline_width=self._ring_w)
                self.create_image(cx, self._cy, image=ring)
            dot = smooth_circle(self, int(self._d), fill=hexcol if self._enabled else c["disabled"],
                                outline=c["outline"], outline_width=1)
            self.create_image(cx, self._cy, image=dot)
        self.create_text(self._text_x, self._cy, anchor="w", text=self._names.get(current, current),
                         fill=c["fg"] if self._enabled else c["disabled"], font=self._font)

    def _on_click(self, event):
        if not self._enabled:
            return
        step = self._d + self._gap
        index = int((event.x - self._pad - self._ring_w + self._gap / 2) // step)
        keys = list(self._swatches)
        if 0 <= index < len(keys) and event.x < self._x0(len(keys) - 1) + self._d + self._gap:
            self._var.set(keys[index])

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self.configure(cursor="hand2" if self._enabled else "arrow")
            self.refresh()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure
