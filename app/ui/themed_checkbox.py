"""tk.Checkbutton with a drawn rounded box and tick instead of the Windows indicator.

Stays a real Checkbutton (same class name, variable, command, state and fg), so code that
walks or recolours checkbuttons keeps working.
"""
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

_SS = 4  # supersampling factor for smooth corners


def _box_image(root, size, gap, border, fill, tick):
    cache = root.__dict__.setdefault("_themed_check_images", {})
    key = (size, gap, border, fill, tick)
    if key in cache:
        return cache[key]
    s = size * _SS
    img = Image.new("RGBA", ((size + gap) * _SS, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(_SS, int(s * 0.09))
    d.rounded_rectangle((w // 2, w // 2, s - 1 - w // 2, s - 1 - w // 2), radius=int(s * 0.22),
                        fill=fill, outline=border, width=w)
    if tick:
        d.line([(s * 0.26, s * 0.52), (s * 0.43, s * 0.69), (s * 0.75, s * 0.33)], fill=tick,
               width=max(_SS, int(s * 0.13)), joint="curve")
    img = img.resize((size + gap, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img, master=root)
    cache[key] = photo
    return photo


_TAG = "ThemedCheckbutton"


def _block_if_disabled(event):
    return "break" if getattr(event.widget, "_disabled", False) else None


def _parent_bg(parent):
    try:
        return parent.cget("bg")
    except tk.TclError:
        from tkinter import ttk
        try:
            style = parent.cget("style") or parent.winfo_class()
        except tk.TclError:
            style = parent.winfo_class()
        return ttk.Style().lookup(style, "background") or "#1e1e1e"


class ThemedCheckbutton(tk.Checkbutton):
    # Tk draws a stipple over images on a disabled widget, so "disabled" is emulated: the Tk
    # state stays normal while clicks are blocked and cget('state') reports "disabled".

    def __init__(self, parent, accent=None, scale=None, **kw):
        if accent is None or scale is None:
            from config import load_theme, scaled_px
            from ui.themed_slider import slider_colors
            accent = accent or slider_colors(load_theme())["accent"]
            scale = scale or scaled_px(100) / 100
        size = max(12, int(15 * scale))
        root = parent._root()
        gap = int(6 * scale) if kw.get("text") else 0
        self._images = {
            False: (_box_image(root, size, gap, "#8a8a8a", "#151515", None),
                    _box_image(root, size, gap, accent, accent, "#101010")),
            True: (_box_image(root, size, gap, "#4a4a4a", "#151515", None),
                   _box_image(root, size, gap, "#555555", "#555555", "#8a8a8a")),
        }
        self._disabled = kw.pop("state", "normal") == "disabled"
        self._fg = kw.pop("fg", kw.pop("foreground", "#e0e0e0"))
        self._active_fg = kw.pop("activeforeground", self._fg)
        self._disabled_fg = kw.pop("disabledforeground", "#666666")
        bg = kw.get("bg", kw.get("background")) or _parent_bg(parent)
        kw.update(compound="left", indicatoron=False, bd=0, highlightthickness=0,
                  offrelief="flat", overrelief="flat", relief="flat", bg=bg)
        kw.pop("background", None)
        # Without the indicator these colour the whole widget, so keep them flat
        kw["selectcolor"] = kw["activebackground"] = bg
        super().__init__(parent, **kw)
        if not root.__dict__.get("_themed_check_tag_bound"):
            for seq in ("<Button-1>", "<ButtonRelease-1>", "<space>"):
                self.bind_class(_TAG, seq, _block_if_disabled)
            root._themed_check_tag_bound = True
        self.bindtags((_TAG,) + self.bindtags())
        self._apply_look()

    def _apply_look(self):
        off, on = self._images[self._disabled]
        fg = self._disabled_fg if self._disabled else self._fg
        super().configure(image=off, selectimage=on, fg=fg,
                          activeforeground=self._disabled_fg if self._disabled else self._active_fg,
                          cursor="arrow" if self._disabled else "hand2")

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        look = False
        if "state" in kw:
            self._disabled = kw.pop("state") == "disabled"
            look = True
        for key in ("fg", "foreground"):
            if key in kw:
                self._fg = kw.pop(key)
                look = True
        if "activeforeground" in kw:
            self._active_fg = kw.pop("activeforeground")
            look = True
        if "disabledforeground" in kw:
            self._disabled_fg = kw.pop("disabledforeground")
            look = True
        if "bg" in kw or "background" in kw:
            bg = kw.get("bg", kw.get("background"))
            kw["selectcolor"] = kw["activebackground"] = bg
        result = super().configure(**kw) if (kw or not look) else None
        if look:
            self._apply_look()
        return result

    config = configure

    def cget(self, key):
        if key == "state":
            return "disabled" if self._disabled else "normal"
        if key in ("fg", "foreground"):
            return self._fg
        if key == "activeforeground":
            return self._active_fg
        return super().cget(key)

    __getitem__ = cget

    def invoke(self):
        if not self._disabled:
            return super().invoke()
