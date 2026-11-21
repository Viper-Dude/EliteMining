"""On-screen text overlays (announcements and cargo) and Elite Dangerous window lookups."""

import logging
import tkinter as tk

from localization import t

log = logging.getLogger("EliteMining")


def _foreground_window_title() -> str:
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def is_game_focused() -> bool:
    """Check if Elite Dangerous game client is the active foreground window."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return "Elite - Dangerous" in buf.value
    except Exception:
        return False


def _find_game_window_rect():
    """Find the Elite Dangerous game window rectangle (left, top, right, bottom).
    Returns None if the game window is not found."""
    try:
        import ctypes
        import ctypes.wintypes

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        result = [None]

        def enum_cb(hwnd, _lparam):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if "Elite - Dangerous" in buf.value:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    result[0] = (rect.left, rect.top, rect.right, rect.bottom)
                    return False  # stop enumerating
            return True

        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return result[0]
    except Exception:
        return None


def get_game_monitor_offset():
    """Return (x_offset, y_offset, screen_width) of the monitor the game is running on.
    Falls back to (0, 0, primary_width) if game window not found."""
    rect = _find_game_window_rect()
    if rect:
        # Use top-left of game window as the monitor origin
        # For fullscreen/borderless, this is the monitor's top-left corner
        game_left, game_top, game_right, _game_bottom = rect
        game_width = game_right - game_left
        return (game_left, game_top, game_width)
    return (0, 0, None)  # None = use default screen width


# --- Text Overlay class for TTS announcements ---
class TextOverlay:
    def __init__(self):
        self.overlay_window = None
        self.overlay_enabled = False
        self.display_duration = 7000  # 7 seconds in milliseconds
        self.fade_timer = None
        self.transparency = 0.9  # Default transparency (90%)
        self.text_color = "#FFFFFF"  # Default white color
        self.position = "upper_left"  # Fixed position
        self.font_size = 12  # Default font size (Normal)
        self._outline_items = []
        self._game_hidden = False  # Track if hidden due to game focus check
        self._is_showing = False  # Track if overlay is actively displaying a message
    def create_overlay(self):
        """Create the overlay window"""
        if self.overlay_window:
            return
            
        self.overlay_window = tk.Toplevel()
        self.overlay_window.title(t('dialogs.mining_announcements'))
        self.overlay_window.wm_overrideredirect(True)  # Remove window decorations
        self.overlay_window.wm_attributes("-topmost", True)  # Always on top
        
        # Make window background completely transparent
        self.overlay_window.wm_attributes("-transparentcolor", "#000001")  # Use almost-black as transparent
        self.overlay_window.configure(bg="#000001")  # This color becomes transparent
        
        # Position based on setting
        self._set_window_position()
        
        # Create canvas with transparent background
        self.canvas = tk.Canvas(
            self.overlay_window,
            bg="#000001",  # Same as transparent color - will be invisible
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Hide initially
        self.overlay_window.withdraw()
        self._reveal_delayed = True

        # Apply current color and brightness settings
        # self._update_text_color() # No text item yet
        
    def show_message(self, message: str, duration_ms: int = None, ignore_sc_hide: bool = False, wrap_width: int = 700):
        """Display a message in the overlay (duration_ms overrides the default display time;
        ignore_sc_hide keeps it visible even if "Hide overlays in supercruise" is on)"""
        if not self.overlay_enabled:
            return
        self._sc_exempt = ignore_sc_hide
        self._prepare_window(message, wrap_width)

        # Always show message — events come from journal files regardless of which app has focus.
        self._is_showing = True
        if not self._game_hidden and (ignore_sc_hide or not getattr(self, '_sc_hidden', False)) and (ignore_sc_hide or not getattr(self, '_session_hidden', False)):
            self._show_on_top()
            logging.info(f"[OVERLAY] show_message: deiconified, duration={self.display_duration}ms, {self._window_diag()}")
        else:
            logging.info(f"[OVERLAY] show_message: gated (game_hidden={self._game_hidden}, "
                          f"sc_hidden={getattr(self, '_sc_hidden', False)}, "
                          f"session_hidden={getattr(self, '_session_hidden', False)})")

        # Cancel any existing timer
        if self.fade_timer:
            self.overlay_window.after_cancel(self.fade_timer)

        # Schedule hide after display duration
        self.fade_timer = self.overlay_window.after(duration_ms or self.display_duration, self._timed_hide)

    def _prepare_window(self, message: str, wrap_width: int):
        """Get a fresh, correctly sized window with the message drawn on it, ready to show"""
        self._wrap_width = wrap_width

        if not self.overlay_window:
            self.create_overlay()
        else:
            self._ensure_alive()
            if not self._is_showing:
                # A long-lived hidden window can stay "visible" to Windows yet draw nothing; start each message on a fresh one
                flags = (self._game_hidden, getattr(self, '_sc_hidden', False), getattr(self, '_session_hidden', False))
                self.reinstate()
                self._game_hidden, self._sc_hidden, self._session_hidden = flags
            if not self.overlay_window:
                # reinstate() only rebuilds the window while the overlay is enabled
                self.create_overlay()

        # Draw text BEFORE showing window to prevent flicker
        self._draw_text(message)

        # Force canvas to compute bbox so we can size the window correctly
        self.canvas.update_idletasks()
        self._fit_window_to_content()

        # A window whose final size differs from the size it was created at renders enlarged/clipped,
        # so rebuild it at the needed size (e.g. the wide Auto Prices table) instead of resizing it
        desired = (max(750, self._fit_size[0]), max(300, self._fit_size[1]))
        if desired != getattr(self, '_base_size', (750, 300)):
            self._base_size = desired
            flags = (self._game_hidden, getattr(self, '_sc_hidden', False), getattr(self, '_session_hidden', False))
            self.reinstate()
            self._game_hidden, self._sc_hidden, self._session_hidden = flags
            if not self.overlay_window:
                self.create_overlay()
            self._draw_text(message)
            self.canvas.update_idletasks()
            self._fit_window_to_content()

        # CRITICAL: Reposition window every time before showing (Windows can reset position)
        self._set_window_position()

    def show_persistent_message(self, message: str, max_lifetime_ms: int = 120000):
        """Display a message that stays visible until manually hidden (for cargo full prompt).

        max_lifetime_ms is a safety cap: if the caller never hides this overlay
        (e.g. the owning dialog never fires its callback), it auto-hides instead
        of staying stuck on screen indefinitely.
        """
        if not self.overlay_enabled:
            return

        self._prepare_window(message, 700)

        # Show window AFTER text is ready — always show persistent messages.
        self._is_showing = True
        if not self._game_hidden and not getattr(self, '_sc_hidden', False) and not getattr(self, '_session_hidden', False):
            self._show_on_top()
            logging.info(f"[OVERLAY] show_persistent_message: deiconified, watchdog={max_lifetime_ms}ms")
        else:
            logging.info(f"[OVERLAY] show_persistent_message: gated (game_hidden={self._game_hidden}, "
                          f"sc_hidden={getattr(self, '_sc_hidden', False)}, "
                          f"session_hidden={getattr(self, '_session_hidden', False)})")

        # Cancel any existing timer, then arm the safety watchdog
        if self.fade_timer:
            self.overlay_window.after_cancel(self.fade_timer)
        self.fade_timer = self.overlay_window.after(max_lifetime_ms, self._timed_hide)

    def _draw_text(self, message: str):
        """Draw text with outline on canvas"""
        font_spec = ("Consolas", self.font_size, "normal")
        text_color = self._get_current_color()
        wrap_width = getattr(self, '_wrap_width', 700)
        base_x, base_y = 2, 2
        offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (0, -1), (1, 0), (-1, 0)]

        if hasattr(self, '_outline_items') and self._outline_items:
            # Update existing items — avoids delete-all flicker on subsequent updates
            for item in self._outline_items:
                self.canvas.itemconfig(item, text=message, font=font_spec, width=wrap_width)
            self.canvas.itemconfig(self.text_item, text=message, font=font_spec, fill=text_color, width=wrap_width)
        else:
            # First time: create all items
            self._outline_items = []
            for ox, oy in offsets:
                self._outline_items.append(self.canvas.create_text(
                    base_x + ox, base_y + oy,
                    text=message,
                    font=font_spec,
                    fill="black",
                    anchor="nw",
                    justify="left",
                    width=wrap_width
                ))
            self.text_item = self.canvas.create_text(
                base_x, base_y,
                text=message,
                font=font_spec,
                fill=text_color,
                anchor="nw",
                justify="left",
                width=wrap_width
            )
    
    def _fit_window_to_content(self):
        """Resize overlay window to fit current canvas content"""
        if not self.overlay_window:
            return
        gx, gy, gw = get_game_monitor_offset()
        x_pos = gx + 20
        y_pos = gy + 100
        bbox = self.canvas.bbox("all") if hasattr(self, 'canvas') else None
        if (gx, gy, gw) != getattr(self, '_last_logged_pos', None):
            self._last_logged_pos = (gx, gy, gw)
            logging.info(f"[OVERLAY] text overlay position: game rect origin=({gx},{gy}) width={gw}, "
                         f"window at ({x_pos},{y_pos}), font_size={self.font_size}, bbox={bbox}")
        if bbox:
            window_width = max(400, bbox[2] + 30)
            window_height = max(60, bbox[3] + 20)
        else:
            window_width = 750
            window_height = 300
        self._fit_size = (window_width, window_height)
        self.overlay_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
        if hasattr(self, 'canvas'):
            self.canvas.config(width=window_width, height=window_height)
        logging.debug(f"[OVERLAY] fit: bbox={bbox} -> {window_width}x{window_height}+{x_pos}+{y_pos}, "
                     f"wrap={getattr(self, '_wrap_width', 700)}, font_size={self.font_size}")

    def hide_overlay(self):
        """Hide the overlay window"""
        if self.overlay_window:
            self._hide_window()
            self._is_showing = False
            logging.debug("[OVERLAY] hide_overlay: hidden")

    def _hide_window(self):
        self.overlay_window.withdraw()

    def _timed_hide(self):
        """Called when display duration (or the persistent-message watchdog) expires"""
        logging.debug("[OVERLAY] _timed_hide: auto-hide fired")
        self._is_showing = False
        if self.overlay_window:
            self._hide_window()

    def reinstate(self):
        """Tear down and rebuild the overlay window and clear stuck hide flags (recovers a lost/buried overlay)."""
        logging.info(f"[OVERLAY] text overlay reinstate (was game_hidden={self._game_hidden}, "
                     f"sc_hidden={getattr(self, '_sc_hidden', False)}, session_hidden={getattr(self, '_session_hidden', False)}, "
                     f"showing={self._is_showing})")
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except tk.TclError:
                pass  # window already gone
            except Exception:
                logging.exception("[OVERLAY] overlay window destroy failed")
        self.overlay_window = None
        self.fade_timer = None
        self._outline_items = []
        self._is_showing = False
        self._game_hidden = False
        self._sc_hidden = False
        self._session_hidden = False
        if self.overlay_enabled:
            self.create_overlay()

    def _ensure_alive(self):
        """Rebuild the window if Tk lost it."""
        try:
            if not self.overlay_window.winfo_exists():
                raise tk.TclError("window gone")
        except tk.TclError:
            self.reinstate()

    def _window_diag(self) -> str:
        try:
            import ctypes, ctypes.wintypes
            self.overlay_window.update_idletasks()
            hwnd = int(self.overlay_window.wm_frame(), 16)
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            try:
                extra = (f" canvas={self.canvas.winfo_width()}x{self.canvas.winfo_height()} "
                         f"view_origin=({self.canvas.canvasx(0):.0f},{self.canvas.canvasy(0):.0f}) "
                         f"dpi={ctypes.windll.user32.GetDpiForWindow(hwnd)}")
            except Exception:
                extra = ""
            return (f"viewable={self.overlay_window.winfo_viewable()} alpha={self.overlay_window.wm_attributes('-alpha')} "
                    f"topmost={self.overlay_window.wm_attributes('-topmost')} "
                    f"win32_visible={bool(ctypes.windll.user32.IsWindowVisible(hwnd))} "
                    f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})" + extra)
        except Exception as e:
            return f"diag failed: {e}"

    def _show_on_top(self):
        # First show after creation: reveal after a short delay so the window's first-draw outline isn't visible
        delayed = getattr(self, '_reveal_delayed', False)
        window = self.overlay_window
        if delayed:
            self._reveal_delayed = False
            window.wm_attributes("-alpha", 0)
        window.deiconify()
        window.wm_attributes("-topmost", True)
        window.lift()
        if delayed:
            def _reveal():
                try:
                    window.wm_attributes("-alpha", 1)
                    window.wm_attributes("-topmost", True)
                    window.lift()
                    logging.info(f"[OVERLAY] text overlay revealed, {self._window_diag()}")
                except tk.TclError as e:
                    logging.info(f"[OVERLAY] text overlay reveal failed: {e}")
            window.after(60, _reveal)

    def set_enabled(self, enabled: bool):
        """Enable or disable the text overlay"""
        self.overlay_enabled = enabled
        if enabled:
            self.reinstate()
        elif self.overlay_window:
            self.hide_overlay()

    def set_transparency(self, transparency_percent: int):
        """Set text brightness (10-100%)"""
        self.transparency = transparency_percent / 100.0
        if self.overlay_window:
            self._update_text_color()
    
    def set_color(self, color_hex: str):
        """Set the base text color"""
        self.text_color = color_hex
        if self.overlay_window:
            self._update_text_color()
    
    def _get_current_color(self):
        """Calculate text color based on brightness setting"""
        # Parse the base color
        base_color = self.text_color.lstrip('#')
        r = int(base_color[0:2], 16)
        g = int(base_color[2:4], 16) 
        b = int(base_color[4:6], 16)
        
        # Use transparency setting to control brightness (0.1 to 1.0)
        brightness_factor = self.transparency
        
        # Calculate new RGB values
        new_r = int(r * brightness_factor)
        new_g = int(g * brightness_factor)
        new_b = int(b * brightness_factor)
        
        # Ensure we get the full color values
        new_r = min(255, max(0, new_r))
        new_g = min(255, max(0, new_g))
        new_b = min(255, max(0, new_b))
        
        return f"#{new_r:02x}{new_g:02x}{new_b:02x}"

    def _update_text_color(self):
        """Update text color of existing text item"""
        if hasattr(self, 'canvas') and hasattr(self, 'text_item'):
            try:
                final_color = self._get_current_color()
                self.canvas.itemconfig(self.text_item, fill=final_color)
            except Exception as e:
                log.error(f"Error updating text color: {e}")
    
    def set_position(self, position: str):
        """Set overlay position - always upper left"""
        self.position = "upper_left"  # Always use upper left
        if self.overlay_window:
            self._set_window_position()
    
    def set_font_size(self, size: int):
        """Set text font size"""
        self.font_size = size
        if self.overlay_window and hasattr(self, 'canvas'):
            try:
                # Clear items so next _draw_text creates them fresh with new size
                self.canvas.delete("all")
                self._outline_items = []
            except Exception as e:
                log.error(f"Error setting font size: {e}")
    
    def set_display_duration(self, seconds: int):
        """Set how long text stays on screen (5-30 seconds)"""
        self.display_duration = seconds * 1000  # Convert to milliseconds
        # If a message is currently showing, don't interrupt it
        # The new duration will apply to the next message
    
    def _set_window_position(self):
        """Set window position - upper left of the monitor the game is on"""
        if not self.overlay_window:
            return
        
        gx, gy, gw = get_game_monitor_offset()
        window_width, window_height = getattr(self, '_base_size', (750, 300))
        x_pos = gx + 20
        y_pos = gy + 100
        
        self.overlay_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
    
    def show_prospector_overlay(self, evt_data: dict, show_all: bool = False, threshold: float = 0.0, 
                               announce_map: dict = None, min_pct_map: dict = None):
        """
        Display enhanced prospector overlay in game style format.
        
        Args:
            evt_data: Prospector event data from journal
            show_all: If True, show all materials; if False, filter by threshold
            threshold: Default threshold percentage
            announce_map: Dictionary of material names -> enabled status
            min_pct_map: Dictionary of material names -> custom thresholds
        """
        print(f"[ENHANCED OVERLAY] Called with show_all={show_all}, threshold={threshold}")
        
        if not self.overlay_enabled:
            print("[ENHANCED OVERLAY] Overlay not enabled, returning")
            return
            
        if not self.overlay_window:
            self.create_overlay()
        
        # Extract data from event
        materials = evt_data.get("Materials", [])
        motherlode = evt_data.get("MotherlodeMaterial_Localised") or evt_data.get("MotherlodeMaterial")
        content = evt_data.get("Content_Localised") or evt_data.get("Content", "")
        remaining = evt_data.get("Remaining")
        
        print(f"[ENHANCED OVERLAY] Materials count: {len(materials)}, Motherlode: {motherlode}")
        
        # Clean up content string (remove "Material Content: " prefix if present)
        if content and content.lower().startswith("material content"):
            content = content[len("Material Content:"):].strip()
        
        # Format header line with distance if available
        # TODO: Add distance from prospector data when available in journal
        header = "LIMPET (PROSPECTOR)"
        
        # Build the message lines
        lines = [header, ""]  # Empty line after header
        
        # Add motherlode if present (always in cyan)
        if motherlode:
            motherlode_clean = self._clean_material_name(motherlode)
            lines.append(f"MOTHERLODE DETECTED: {motherlode_clean.upper()}")
            lines.append("")  # Empty line after motherlode
        
        # Add remaining percentage
        if remaining is not None:
            if remaining <= 0.0:
                lines.append("MINERALS REMAINING: DEPLETED")
            elif remaining >= 100.0:
                lines.append("MINERALS REMAINING: 100.00%")
            else:
                lines.append(f"MINERALS REMAINING: {remaining:.2f}%")
        else:
            lines.append("MINERALS REMAINING: 100.00%")
        
        # Process materials
        material_lines = []
        for m in materials:
            # Extract material name and percentage
            name = m.get("Name_Localised") or m.get("Name", "")
            name = self._clean_material_name(name)
            pct = m.get("Proportion")
            
            if not name or pct is None:
                continue
            
            # Convert proportion to percentage
            pct_value = pct * 100.0
            
            # Check if we should display this material
            if not show_all:
                # Filter by threshold
                eff_threshold = min_pct_map.get(name, threshold) if min_pct_map else threshold
                is_enabled = announce_map.get(name, False) if announce_map else True
                
                # Also try title case for material name lookup
                if not is_enabled and name != name.title():
                    is_enabled = announce_map.get(name.title(), False) if announce_map else False
                
                # Skip if below threshold or not enabled
                if not is_enabled or pct_value < eff_threshold:
                    continue
            
            # Format material line
            material_lines.append(f"{name.upper()} {pct_value:.2f}%")
        
        # Add material lines
        lines.extend(material_lines)
        
        # Add content line if present
        if content:
            lines.append("")  # Empty line before content
            lines.append(f"MATERIAL CONTENT: {content.upper()}")
        
        # Join all lines
        message = "\n".join(lines)
        
        print(f"[ENHANCED OVERLAY] Displaying {len(lines)} lines")
        print(f"[ENHANCED OVERLAY] Message:\n{message}")
        
        # Show the overlay
        self.show_message(message)
    
    def _clean_material_name(self, name: str) -> str:
        """Clean up material name (remove $, underscores, etc.)"""
        if not name:
            return ""
        # Remove common prefixes
        if name.startswith("$"):
            name = name[1:]
        if name.endswith("_name;"):
            name = name[:-6]
        # Replace underscores with spaces
        name = name.replace("_", " ")
        # Title case
        return name.title()
            
    def destroy(self):
        """Clean up the overlay"""
        if self.overlay_window:
            if self.fade_timer:
                self.overlay_window.after_cancel(self.fade_timer)
            self.overlay_window.destroy()
            self.overlay_window = None
            self._outline_items = []


class CargoTextOverlay:
    """Persistent cargo monitor overlay on the right side of the screen.
    Shares font/color settings with the announcement TextOverlay."""

    def __init__(self):
        self.overlay_window = None
        self.overlay_enabled = False
        self.transparency = 0.9
        self.text_color = "#FFFFFF"
        self.font_size = 12
        self._outline_items = []
        self._drawn_key = None
        self._update_timer = None
        self._game_hidden = False  # Track if hidden due to game focus check
        self.focus_blocked = lambda: False  # set by the app: True while the focus rule says hide

    # -- window management --------------------------------------------------
    def create_overlay(self):
        if self.overlay_window:
            return
        self.overlay_window = tk.Toplevel()
        self.overlay_window.title("Cargo Monitor")
        self.overlay_window.wm_overrideredirect(True)
        self.overlay_window.wm_attributes("-topmost", True)
        self.overlay_window.wm_attributes("-transparentcolor", "#000001")
        self.overlay_window.wm_attributes("-alpha", 0)  # Start hidden
        self.overlay_window.configure(bg="#000001")
        self._set_window_position()
        self.canvas = tk.Canvas(self.overlay_window, bg="#000001",
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)

    def _set_window_position(self):
        """Position fixed-size window anchored to the right side of game monitor."""
        if not self.overlay_window:
            return
        gx, gy, gw = get_game_monitor_offset()
        screen_w = gw if gw else self.overlay_window.winfo_screenwidth()
        # Fixed size — transparent background makes oversized window invisible
        window_width = 700
        window_height = 600
        x_pos = gx + screen_w - window_width - 20
        y_pos = gy + 100
        self.overlay_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

    # -- drawing ------------------------------------------------------------
    def _draw_text(self, message: str):
        font_spec = ("Consolas", self.font_size, "normal")
        text_color = self._get_current_color()
        # Anchor text to the right side of the window (700px wide, minus padding)
        base_x = 700 - 22  # window_width minus padx and margin
        base_y = 2
        offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1),
                   (0, 1), (0, -1), (1, 0), (-1, 0)]
        # Every rebuild path empties _outline_items, so a new or cleared canvas always redraws
        key = (message, self.font_size, text_color)
        if self._outline_items and key == self._drawn_key:
            return
        self._drawn_key = key
        if hasattr(self, '_outline_items') and self._outline_items:
            for item in self._outline_items:
                self.canvas.itemconfig(item, text=message, font=font_spec)
            self.canvas.itemconfig(self.text_item, text=message, font=font_spec, fill=text_color)
        else:
            self._outline_items = []
            for ox, oy in offsets:
                self._outline_items.append(self.canvas.create_text(
                    base_x + ox, base_y + oy,
                    text=message, font=font_spec, fill="black",
                    anchor="ne", justify="left"))
            self.text_item = self.canvas.create_text(
                base_x, base_y, text=message, font=font_spec,
                fill=text_color, anchor="ne", justify="left")

    def _get_current_color(self):
        base = self.text_color.lstrip('#')
        r, g, b = int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16)
        f = self.transparency
        return f"#{min(255,max(0,int(r*f))):02x}{min(255,max(0,int(g*f))):02x}{min(255,max(0,int(b*f))):02x}"

    # -- public API (mirrors TextOverlay settings) --------------------------
    def set_enabled(self, enabled: bool):
        self.overlay_enabled = enabled
        if enabled:
            if not self.overlay_window:
                self.create_overlay()
            # Don't show here — let update_cargo() show it once data is ready
        elif self.overlay_window:
            # Destroy rather than alpha-hide: a hidden leftover window can reappear or render oversized
            try:
                self.overlay_window.destroy()
            except tk.TclError:
                pass  # window already gone
            except Exception:
                logging.exception("[OVERLAY] overlay window destroy failed")
            self.overlay_window = None
            self._outline_items = []

    def reinstate(self):
        """Tear down and rebuild the overlay window from scratch (recovers a lost/buried overlay)."""
        logging.info(f"[OVERLAY] cargo overlay reinstate (was game_hidden={self._game_hidden}, "
                     f"sc_hidden={getattr(self, '_sc_hidden', False)}, session_hidden={getattr(self, '_session_hidden', False)})")
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except tk.TclError:
                pass  # window already gone
            except Exception:
                logging.exception("[OVERLAY] overlay window destroy failed")
        self.overlay_window = None
        self._outline_items = []
        self._game_hidden = False
        self._sc_hidden = False
        self._session_hidden = False
        if self.overlay_enabled:
            self.create_overlay()

    def _ensure_alive(self):
        """Rebuild the window if Tk lost it."""
        try:
            if not self.overlay_window.winfo_exists():
                raise tk.TclError("window gone")
        except tk.TclError:
            self.reinstate()

    def set_transparency(self, transparency_percent: int):
        self.transparency = transparency_percent / 100.0

    def set_color(self, color_hex: str):
        self.text_color = color_hex

    def set_font_size(self, size: int):
        self.font_size = size
        # Clear canvas items so _draw_text creates fresh ones with new font size
        if hasattr(self, 'canvas') and self._outline_items:
            self.canvas.delete("all")
            self._outline_items = []

    # -- cargo data update --------------------------------------------------
    def update_cargo(self, cargo_monitor, tph=None):
        """Build text from cargo_monitor data and redraw."""
        if not self.overlay_enabled:
            return
        if not self.overlay_window:
            self.create_overlay()
        else:
            self._ensure_alive()

        lines = []
        cargo = cargo_monitor
        pct = (cargo.current_cargo / cargo.max_cargo * 100) if cargo.max_cargo > 0 else 0

        header = f"CARGO STATUS  {cargo.current_cargo}/{cargo.max_cargo}t  ({pct:.0f}%)"
        header_len = len(header)
        lines.append(header)

        if tph and tph > 0:
            tph_prefix, tph_suffix = t('settings.overlay_tph_line').split('{tph}')
            lines.append(f"{tph_prefix:<17}{tph:>4.0f}{tph_suffix}".ljust(header_len))

        if cargo.cargo_items:
            sorted_items = sorted(cargo.cargo_items.items(),
                                  key=lambda x: (x[0].lower() != 'limpet', -x[1]))
            for name, qty in sorted_items:
                display = name.replace('_', ' ').replace('$', '').title()
                is_limpet = "limpet" in name.lower()
                if is_limpet:
                    display = "Limpet"
                if display in ('Low Temp. Diamonds', 'Low Temperature Diamonds'):
                    display = 'LTD'
                cargo_line = f"{display:<14}   {qty:>4}t"
                lines.append(cargo_line.ljust(header_len))
        else:
            if cargo.current_cargo > 0:
                lines.append(f"{cargo.current_cargo}t total")
            else:
                lines.append("Empty")

        if cargo.materials_collected:
            lines.append("")
            lines.append("ENGINEERING MATERIALS".ljust(header_len))
            sorted_mats = sorted(cargo.materials_collected.items(), key=lambda x: x[0])
            for mat_name, qty in sorted_mats:
                grade = cargo.MATERIAL_GRADES.get(mat_name, 0)
                display = cargo.materials_localized_names.get(mat_name, mat_name)
                mat_line = f"{display:<14} G{grade}  {qty:>3}"
                lines.append(mat_line.ljust(header_len))

        message = "\n".join(lines)
        self._draw_text(message)
        if self.overlay_enabled and not self._game_hidden and not getattr(self, '_sc_hidden', False) and not getattr(self, '_session_hidden', False) \
                and _find_game_window_rect() is not None and not self.focus_blocked():
            self.overlay_window.wm_attributes("-alpha", 1)

    def destroy(self):
        if self._update_timer:
            try:
                self.overlay_window.after_cancel(self._update_timer)
            except tk.TclError:
                pass  # window already gone
            except Exception:
                logging.exception("[OVERLAY] cargo overlay timer cancel failed")
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None
            self._outline_items = []
