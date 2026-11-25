"""Segmented pick-one control: the selected segment is filled with the accent colour."""
import tkinter as tk
import tkinter.font as tkfont

from ui.themed_slider import text_on


def view_switch_style(theme, scaled_font, scaled_px):
    """Colours/font for a gapped view switch: rounded like the Modern action buttons in Modern themes,
    with the selected segment toned towards the button grey so it doesn't shout."""
    from ui.themed_slider import slider_colors
    if theme not in ("modern", "modern_slate", "modern_orange"):
        return dict(accent=slider_colors(theme)["accent"], font=scaled_font(8))
    from ui.theme import get_theme_colors
    c = get_theme_colors(theme)
    # Modern Dark is neutral grey, so it uses its own grey accent instead of the slider blue
    base, weight = (c["accent"], 1 / 3) if theme == "modern_slate" else (slider_colors(theme)["accent"], 1 / 2)
    grey = c["btn_bg"]
    soft = "#" + "".join(f"{round(int(base[i:i + 2], 16) * weight + int(grey[i:i + 2], 16) * (1 - weight)):02x}"
                         for i in (1, 3, 5))
    return dict(track=grey, accent=soft, fg=c["fg"], selected_fg=c["fg_bright"], outline=c["border"],
                font=scaled_font(9), radius=scaled_px(6))


class SegmentedSelector(tk.Canvas):
    def __init__(self, parent, choices, variable, bg="#1e1e1e", track="#3a3a3a", accent="#ff8c00",
                 fg="#ffffff", selected_fg=None, disabled="#666666", font=None, scale=1.0, gap=0, radius=0,
                 outline=""):
        self._choices = list(choices)
        self._radius = int(radius)
        self._var = variable
        self._enabled = True
        self._font = font
        self._colors = dict(track=track, accent=accent, fg=fg, selected_fg=selected_fg or text_on(accent),
                            disabled=disabled)
        self._outline = outline
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

    def _rounded(self, x0, y0, x1, y1, fill, outline):
        """Rounded box drawn the same way as the Modern RoundedButton, so both look alike."""
        r = self._radius
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, fill=fill, outline=outline)

    def refresh(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        c = self._colors
        m = self._m
        if self._radius and self._gap:
            # Each segment is its own rounded button; the selected one is filled with the accent
            current = self._var.get()
            for i, (key, label) in enumerate(self._choices):
                left = i * self._step
                selected = key == current
                fill = (c["accent"] if self._enabled else c["disabled"]) if selected else c["track"]
                self._rounded(left + 1, 1, left + self._seg_w + 2 * m - 1, self._h + 2 * m - 1,
                              fill, fill if selected else (self._outline or c["track"]))
                if self._enabled:
                    color = c["selected_fg"] if selected else c["fg"]
                else:
                    color = c["track"] if selected else c["disabled"]
                self.create_text(left + m + self._seg_w / 2, m + self._h / 2, text=label, fill=color,
                                 font=self._font)
            return
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

    def segment_at(self, x):
        """Key of the segment under canvas x, or None (outside or in a gap)."""
        index = int((x - self._m) // self._step)
        if self._gap and (x - self._m) - index * self._step > self._seg_w:
            return None
        if 0 <= index < len(self._choices):
            return self._choices[index][0]
        return None

    def _on_click(self, event):
        if not self._enabled:
            return
        key = self.segment_at(event.x)
        if key is not None:
            self._var.set(key)

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
