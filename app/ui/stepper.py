"""Flat number stepper: [-] value [+] with wheel, arrow keys and press-and-hold (replaces tk.Spinbox)."""
import tkinter as tk

from ui.themed_slider import text_on


class Stepper(tk.Frame):
    _REPEAT_DELAY = 400
    _REPEAT_INTERVAL = 80

    def __init__(self, parent, from_, to, variable, increment=1, width=4, command=None, bg="#1e1e1e",
                 field_bg="#1e1e1e", button_bg="#3a3a3a", accent="#ff8c00", fg="#ffffff",
                 disabled="#666666", font=None, scale=1.0):
        super().__init__(parent, bg=bg, highlightthickness=1, highlightbackground=button_bg,
                         highlightcolor=button_bg, bd=0)
        self._lo, self._hi, self._step = from_, to, increment
        self._var = variable
        self._command = command
        self._last_good = None
        self._enabled = True
        self._repeat_job = None
        self._colors = dict(button_bg=button_bg, accent=accent, fg=fg, disabled=disabled, field_bg=field_bg)
        btn_w = int(22 * scale)
        self._minus = tk.Label(self, text="−", bg=button_bg, fg=fg, font=font, width=2, cursor="hand2")
        self._entry = tk.Entry(self, textvariable=variable, width=width, justify="center", bg=field_bg, fg=fg,
                               insertbackground=fg, disabledbackground=field_bg, disabledforeground=disabled,
                               selectbackground="#4a6a8a", relief="flat", bd=0, highlightthickness=0, font=font)
        self._plus = tk.Label(self, text="+", bg=button_bg, fg=fg, font=font, width=2, cursor="hand2")
        self._minus.pack(side="left", fill="y", ipadx=max(0, (btn_w - 16) // 2))
        self._entry.pack(side="left", fill="both", expand=True, ipady=int(2 * scale))
        self._plus.pack(side="left", fill="y", ipadx=max(0, (btn_w - 16) // 2))
        for btn, direction in ((self._minus, -1), (self._plus, 1)):
            btn.bind("<ButtonPress-1>", lambda e, d=direction: self._press(d))
            btn.bind("<ButtonRelease-1>", lambda e: self._release())
            btn.bind("<Enter>", lambda e, b=btn: self._hover(b, True))
            btn.bind("<Leave>", lambda e, b=btn: (self._hover(b, False), self._release()))
        for w in (self, self._minus, self._entry, self._plus):
            w.bind("<MouseWheel>", self._on_wheel)
        self._entry.bind("<Up>", lambda e: (self._nudge(1), "break")[1])
        self._entry.bind("<Down>", lambda e: (self._nudge(-1), "break")[1])
        self._entry.bind("<Return>", lambda e: self._clamp())
        self._entry.bind("<FocusOut>", lambda e: self._clamp())
        self._trace = variable.trace_add("write", lambda *_: self._current())
        self.bind("<Destroy>", self._on_destroy)
        self._current()

    def _on_destroy(self, event):
        if event.widget is self:
            try:
                self._var.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass

    @property
    def entry(self):
        return self._entry

    def _current(self):
        try:
            self._last_good = float(self._var.get())
        except (tk.TclError, ValueError):
            pass
        return self._last_good if self._last_good is not None else float(self._lo)

    def _set(self, value):
        value = max(self._lo, min(self._hi, value))
        if isinstance(self._step, int) and isinstance(self._lo, int):
            value = int(round(value))
        else:
            value = round(value, 1)
        self._var.set(value)
        if self._command:
            self._command()

    def _nudge(self, direction):
        if self._enabled:
            self._set(self._current() + direction * self._step)

    def _clamp(self):
        if self._enabled:
            self._set(self._current())

    def _press(self, direction):
        if not self._enabled:
            return
        self._nudge(direction)
        self._repeat_job = self.after(self._REPEAT_DELAY, lambda: self._repeat(direction))

    def _repeat(self, direction):
        self._nudge(direction)
        self._repeat_job = self.after(self._REPEAT_INTERVAL, lambda: self._repeat(direction))

    def _release(self):
        if self._repeat_job:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None

    def _hover(self, btn, inside):
        if not self._enabled:
            return
        c = self._colors
        btn.configure(bg=c["accent"] if inside else c["button_bg"], fg=text_on(c["accent"]) if inside else c["fg"])

    def _on_wheel(self, event):
        self._nudge(1 if event.delta > 0 else -1)
        return "break"

    def get(self):
        return self._var.get()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self._release()
            c = self._colors
            fg = c["fg"] if self._enabled else c["disabled"]
            for btn in (self._minus, self._plus):
                btn.configure(bg=c["button_bg"], fg=fg, cursor="hand2" if self._enabled else "arrow")
            self._entry.configure(state="normal" if self._enabled else "disabled")
        for key in ("fg", "insertbackground"):
            if key in kw:
                value = kw.pop(key)
                self._entry.configure(**{key: value})
                if key == "fg":
                    self._colors["fg"] = value
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure
