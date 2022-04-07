# register for usb device change notifications
import uuid
import ctypes
from ctypes import *
from ctypes import wintypes


if sizeof(c_long) == sizeof(c_void_p):
    UINT_PTR = c_ulong
    LONG_PTR = c_long
    ULONG_PTR = c_ulong
elif sizeof(c_longlong) == sizeof(c_void_p):
    UINT_PTR = c_ulonglong
    LONG_PTR = c_longlong
    ULONG_PTR = c_ulonglong
else:
    UINT_PTR = c_ulong
    LONG_PTR = c_long
    ULONG_PTR = c_ulong

UINT = c_uint
HANDLE = c_void_p
HWND = HANDLE
WPARAM = UINT_PTR
LPARAM = LONG_PTR
LRESULT = LONG_PTR

GWL_WNDPROC = -4
WM_DESTROY = 2
DBT_DEVTYP_DEVICEINTERFACE = 0x00000005  # device interface class
DEVICE_NOTIFY_WINDOW_HANDLE = 0
DEVICE_NOTIFY_ALL_INTERFACE_CLASSES = 4
DBT_DEVICEREMOVECOMPLETE = 0x8004  # device is gone
DBT_DEVICEARRIVAL = 0x8000  # system detected a new device
WM_DEVICECHANGE = 0x0219

# Windows device GUID to filter on
GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"

## Create a type that will be used to cast a python callable to a c callback function
## first arg is return type, the rest are the arguments
WndProcType = ctypes.WINFUNCTYPE(c_int, HWND, UINT, WPARAM, LPARAM)


SetWindowLongPtr = ctypes.windll.user32.SetWindowLongPtrW
SetWindowLongPtr.argtypes = [HWND, c_int, WndProcType]
SetWindowLongPtr.restype = LONG_PTR

CallWindowProc = ctypes.windll.user32.CallWindowProcW
CallWindowProc.argtypes = [LONG_PTR, HWND, UINT, WPARAM, LPARAM]
CallWindowProc.restype = LRESULT

DefWindowProc = ctypes.windll.user32.DefWindowProcW
DefWindowProc.argtypes = [HWND, UINT, WPARAM, LPARAM]
DefWindowProc.restype = LRESULT


RegisterDeviceNotification = ctypes.windll.user32.RegisterDeviceNotificationW
RegisterDeviceNotification.restype = HWND
RegisterDeviceNotification.argtypes = [HWND, c_void_p, wintypes.DWORD]

UnregisterDeviceNotification = ctypes.windll.user32.UnregisterDeviceNotification
UnregisterDeviceNotification.restype = wintypes.BOOL
UnregisterDeviceNotification.argtypes = [HWND]


class DEV_BROADCAST_DEVICEINTERFACE(ctypes.Structure):
    _fields_ = [
        ("dbcc_size", ctypes.c_ulong),
        ("dbcc_devicetype", ctypes.c_ulong),
        ("dbcc_reserved", ctypes.c_ulong),
        ("dbcc_classguid", ctypes.c_char * 16),
        ("dbcc_name", ctypes.c_wchar * 256),
    ]


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD),
    ]


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD),
    ]


__handle = None
__oldWndProc = None
__callback = None
__localWndProcWrapped = None


def localWndProc(hWnd, msg, wParam, lParam):
    if msg == WM_DEVICECHANGE:
        details = cast(lParam, POINTER(DEV_BROADCAST_HDR))
        if details.contents.dbch_devicetype == DBT_DEVTYP_DEVICEINTERFACE:
            details = cast(lParam, POINTER(DEV_BROADCAST_DEVICEINTERFACE))
            # For some reason filtering by GUID in RegisterDeviceNotification stopped
            # working, notifying on everything and filtering the guid here works instead
            if GUID_DEVINTERFACE_USB_DEVICE.lower() in details.contents.dbcc_name:
                if wParam in (DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE):
                    __callback(attach=(wParam == DBT_DEVICEARRIVAL))

    if msg == WM_DESTROY:
        unhookWndProc()

    ret = CallWindowProc(__oldWndProc, hWnd, msg, wParam, lParam)
    # ret = DefWindowProc(hWnd, msg, wParam, lParam)
    return ret


def unhookWndProc():
    global __localWndProcWrapped, __oldWndProc, __handle
    SetWindowLongPtr(__handle, GWL_WNDPROC, WndProcType(__oldWndProc))

    ## Allow the ctypes wrapper to be garbage collected
    __localWndProcWrapped = None


def registerDeviceNotification(
    handle, callback, guid=None, devicetype=DBT_DEVTYP_DEVICEINTERFACE
):
    global __callback, __oldWndProc, __localWndProcWrapped, __handle

    devIF = DEV_BROADCAST_DEVICEINTERFACE()
    devIF.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE)
    devIF.dbcc_devicetype = devicetype

    flags = DEVICE_NOTIFY_WINDOW_HANDLE
    if guid:
        devIF.dbcc_classguid = uuid.UUID(guid).bytes
    else:
        flags |= DEVICE_NOTIFY_ALL_INTERFACE_CLASSES

    ret = RegisterDeviceNotification(handle, ctypes.byref(devIF), flags)
    
    __handle = handle
    __callback = callback

    __localWndProcWrapped = WndProcType(localWndProc)
    __oldWndProc = SetWindowLongPtr(handle, GWL_WNDPROC, __localWndProcWrapped)

    return ret


def unregisterDeviceNotification(handle):
    if UnregisterDeviceNotification(handle) == 0:
        raise Exception("Unable to unregister device notification messages")
