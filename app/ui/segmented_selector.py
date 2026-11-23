"""Segmented pick-one control: the selected segment is filled with the accent colour."""
import tkinter as tk
import tkinter.font as tkfont

from ui.themed_slider import text_on


class SegmentedSelector(tk.Canvas):
    def __init__(self, parent, choices, variable, bg="#1e1e1e", track="#3a3a3a", accent="#ff8c00",
                 fg="#ffffff", selected_fg=None, disabled="#666666", font=None, scale=1.0, gap=0):
        self._choices = list(choices)
        self._var = variable
        self._enabled = True
        self._font = font
        self._colors = dict(track=track, accent=accent, fg=fg, selected_fg=selected_fg or text_on(accent),
                            disabled=disabled)
        self._outline = ""
        pad = int(10 * scale)
        try:
            measure = tkfont.Font(font=font).measure
            self._seg_w = max(measure(label) for _, label in self._choices) + 2 * pad
        except tk.TclError:
            self._seg_w = int(80 * scale)
        self._h = int(21 * scale)
        self._m = max(2, int(2 * scale))
        # gap > 0 draws each segment as its own block with that much space between them
        self._gap = gap
        self._step = self._seg_w + 2 * self._m + gap if gap else self._seg_w
        width = (self._step * len(self._choices) - gap) if gap else self._seg_w * len(self._choices) + 2 * self._m
        super().__init__(parent, width=width, height=self._h + 2 * self._m,
                         bg=bg, highlightthickness=0, bd=0, cursor="hand2")
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

    def refresh(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        c = self._colors
        m = self._m
        blocks = ([(i * self._step, self._seg_w) for i in range(len(self._choices))] if self._gap
                  else [(0, self._seg_w * len(self._choices))])
        for left, width in blocks:
            self.create_rectangle(left, 0, left + width + 2 * m, self._h + 2 * m,
                                  fill=self._outline or c["track"], outline="")
            if self._outline:
                self.create_rectangle(left + m, m, left + width + m, self._h + m, fill=c["track"], outline="")
        current = self._var.get()
        for i, (key, label) in enumerate(self._choices):
            x0 = m + i * self._step
            selected = key == current
            if selected:
                self.create_rectangle(x0, m, x0 + self._seg_w, m + self._h,
                                      fill=c["accent"] if self._enabled else c["disabled"], outline="")
            if self._enabled:
                color = c["selected_fg"] if selected else c["fg"]
            else:
                color = c["track"] if selected else c["disabled"]
            self.create_text(x0 + self._seg_w / 2, m + self._h / 2, text=label, fill=color, font=self._font)

    def _on_click(self, event):
        if not self._enabled:
            return
        index = int((event.x - self._m) // self._step)
        if self._gap and (event.x - self._m) - index * self._step > self._seg_w:
            return  # click landed in the gap
        if 0 <= index < len(self._choices):
            self._var.set(self._choices[index][0])

    def configure(self, cnf=None, **kw):
        # outline: border colour around the control (e.g. "changed since preset save"); "" for none
        if "outline" in kw:
            self._outline = kw.pop("outline") or ""
            self.refresh()
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self.configure(cursor="hand2" if self._enabled else "arrow")
            self.refresh()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure
