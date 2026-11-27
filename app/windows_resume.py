import ctypes
from ctypes import wintypes
import logging


log = logging.getLogger('EliteMining')
WM_POWERBROADCAST = 0x0218
WM_NCDESTROY = 0x0082
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
GA_ROOT = 2
DEVICE_NOTIFY_WINDOW_HANDLE = 0


def watch_windows_resume(window, on_resume, on_suspend):
    """Return a native callback that the caller keeps alive with the Tk window."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    comctl32 = ctypes.WinDLL('comctl32')
    message_args = (wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
    subclass_proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, *message_args, ctypes.c_size_t, ctypes.c_size_t)

    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.RegisterSuspendResumeNotification.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    user32.RegisterSuspendResumeNotification.restype = wintypes.HANDLE
    user32.UnregisterSuspendResumeNotification.argtypes = (wintypes.HANDLE,)
    user32.UnregisterSuspendResumeNotification.restype = wintypes.BOOL
    comctl32.SetWindowSubclass.argtypes = (wintypes.HWND, subclass_proc, ctypes.c_size_t, ctypes.c_size_t)
    comctl32.SetWindowSubclass.restype = wintypes.BOOL
    comctl32.RemoveWindowSubclass.argtypes = (wintypes.HWND, subclass_proc, ctypes.c_size_t)
    comctl32.RemoveWindowSubclass.restype = wintypes.BOOL
    comctl32.DefSubclassProc.argtypes = message_args
    comctl32.DefSubclassProc.restype = ctypes.c_ssize_t

    # Tk's widget HWND is a child of the top-level window that receives broadcasts.
    hwnd = user32.GetAncestor(window.winfo_id(), GA_ROOT)
    registration = None

    @subclass_proc
    def handle_message(hwnd, message, wparam, lparam, subclass_id, _ref_data):
        if message == WM_POWERBROADCAST:
            try:
                if wparam == PBT_APMRESUMEAUTOMATIC:
                    on_resume()
                elif wparam == PBT_APMSUSPEND:
                    on_suspend()
            except Exception:
                log.exception('Could not handle Windows sleep or wake notification')
        elif message == WM_NCDESTROY:
            on_suspend()
            if registration:
                user32.UnregisterSuspendResumeNotification(registration)
            comctl32.RemoveWindowSubclass(hwnd, handle_message, subclass_id)
        return comctl32.DefSubclassProc(hwnd, message, wparam, lparam)

    if not hwnd or not comctl32.SetWindowSubclass(hwnd, handle_message, 0, 0):
        log.warning('Could not attach the Windows wake handler')
        return None

    registration = user32.RegisterSuspendResumeNotification(hwnd, DEVICE_NOTIFY_WINDOW_HANDLE)
    if not registration:
        log.warning('Could not register for Windows suspend/resume notifications (error %s)', ctypes.get_last_error())
    return handle_message
