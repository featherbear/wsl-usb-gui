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
DBT_DEVICEREMOVECOMPLETE = 0x8004  # device is gone
DBT_DEVICEARRIVAL = 0x8000  # system detected a new device
WM_DEVICECHANGE = 0x0219

# Change the following guid to the GUID of the device you want notifications for
GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
# GUID_DEVINTERFACE_USB_DEVICE = "{3c5e1462-5695-4e18-876b-f3f3d08aaf18}"

## Create a type that will be used to cast a python callable to a c callback function
## first arg is return type, the rest are the arguments
WndProcType = ctypes.WINFUNCTYPE(c_int, HWND, UINT, WPARAM, LPARAM)


SetWindowLongPtr = ctypes.windll.user32.SetWindowLongPtrA
SetWindowLongPtr.argtypes = [HWND, c_int, WndProcType]
SetWindowLongPtr.restype = LONG_PTR

CallWindowProc = ctypes.windll.user32.CallWindowProcA
CallWindowProc.argtypes = [LONG_PTR, HWND, UINT, WPARAM, LPARAM]
CallWindowProc.restype = LRESULT

DefWindowProcA = ctypes.windll.user32.DefWindowProcA
DefWindowProcA.argtypes = [HWND, UINT, WPARAM, LPARAM]
DefWindowProcA.restype = LRESULT


RegisterDeviceNotification = ctypes.windll.user32.RegisterDeviceNotificationW
RegisterDeviceNotification.restype = wintypes.HANDLE
RegisterDeviceNotification.argtypes = [wintypes.HANDLE, c_void_p, wintypes.DWORD]

UnregisterDeviceNotification = ctypes.windll.user32.UnregisterDeviceNotification
UnregisterDeviceNotification.restype = wintypes.BOOL
UnregisterDeviceNotification.argtypes = [wintypes.HANDLE]


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


__handle = None
__oldWndProc = None
__callback = None
__localWndProcWrapped = None


def localWndProc(hWnd, msg, wParam, lParam):
    if msg == WM_DEVICECHANGE:
        if wParam in (DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE):
            __callback(attach=(wParam == DBT_DEVICEARRIVAL))

    if msg == WM_DESTROY:
        unhookWndProc()

    # ret = CallWindowProc(__oldWndProc, hWnd, msg, wParam, lParam)
    ret = DefWindowProcA(hWnd, msg, wParam, lParam)
    return ret


def unhookWndProc():
    global __localWndProcWrapped, __oldWndProc, __handle
    SetWindowLongPtr(__handle, GWL_WNDPROC, __oldWndProc)

    ## Allow the ctypes wrapper to be garbage collected
    __localWndProcWrapped = None


def registerDeviceNotification(
    handle, callback, guid=GUID_DEVINTERFACE_USB_DEVICE, devicetype=DBT_DEVTYP_DEVICEINTERFACE
):
    global __callback, __oldWndProc, __localWndProcWrapped, __handle

    devIF = DEV_BROADCAST_DEVICEINTERFACE()
    devIF.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE)
    devIF.dbcc_devicetype = devicetype

    devIF.dbcc_classguid = uuid.UUID(guid).bytes

    __handle = handle
    __callback = callback

    __localWndProcWrapped = WndProcType(localWndProc)
    __oldWndProc = SetWindowLongPtr(handle, GWL_WNDPROC, __localWndProcWrapped)

    return RegisterDeviceNotification(handle, ctypes.byref(devIF), 0)


def unregisterDeviceNotification(handle):
    if UnregisterDeviceNotification(handle) == 0:
        raise Exception("Unable to unregister device notification messages")
