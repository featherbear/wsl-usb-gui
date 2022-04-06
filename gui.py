#requires python 3.8+ may work on 3.6, 3.7 definitely broken on <= 3.5 due to subprocess args (text=True)
import os
from tkinter import *
from tkinter.ttk import *
from tkinter.messagebox import showwarning
import json
import subprocess
import sys
import re
import time
from urllib.parse import urlparse
from collections import namedtuple
from pathlib import Path
from typing import *
import appdirs


WSL = os.environ.get('WSL_INTEROP', False)

DEVICE_COLUMNS = ["bus_id", "description"]
DEVICE_COLUMN_WIDTHS = [50, 50]
ATTACHED_COLUMNS = ["bus_id", "description"] #, "client"]
ATTACHED_COLUMN_WIDTHS = [20, 80, 20]
USBIPD_PORT = 3240
CONFIG_FILE = Path(appdirs.user_data_dir("wsl-usb-gui", "")) / "config.json"

attached_devices = {}
pinned_profiles = []

# register for device change notifications
import uuid
import ctypes
from ctypes import wintypes, c_void_p

# GWL_WNDPROC = -4
WM_DESTROY  = 2
DBT_DEVTYP_DEVICEINTERFACE = 0x00000005  # device interface class
DBT_DEVICEREMOVECOMPLETE = 0x8004  # device is gone
DBT_DEVICEARRIVAL = 0x8000  # system detected a new device
WM_DEVICECHANGE = 0x0219

SetWindowLong = ctypes.windll.user32.SetWindowLongW
CallWindowProc = ctypes.windll.user32.CallWindowProcW

## Create a type that will be used to cast a python callable to a c callback function
## first arg is return type, the rest are the arguments
#WndProcType = ctypes.WINFUNCTYPE(c_int, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
WndProcType = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_int)

RegisterDeviceNotification = ctypes.windll.user32.RegisterDeviceNotificationW
RegisterDeviceNotification.restype = wintypes.HANDLE
RegisterDeviceNotification.argtypes = [wintypes.HANDLE, c_void_p, wintypes.DWORD]

UnregisterDeviceNotification = ctypes.windll.user32.UnregisterDeviceNotification
UnregisterDeviceNotification.restype = wintypes.BOOL
UnregisterDeviceNotification.argtypes = [wintypes.HANDLE]

class DEV_BROADCAST_DEVICEINTERFACE(ctypes.Structure):
    _fields_ = [("dbcc_size", ctypes.c_ulong),
                  ("dbcc_devicetype", ctypes.c_ulong),
                  ("dbcc_reserved", ctypes.c_ulong),
                  ("dbcc_classguid", ctypes.c_char * 16),
                  ("dbcc_name", ctypes.c_wchar * 256)]

class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [("dbch_size", wintypes.DWORD),
                ("dbch_devicetype", wintypes.DWORD),
                ("dbch_reserved", wintypes.DWORD)]


def registerDeviceNotification(guid, devicetype=DBT_DEVTYP_DEVICEINTERFACE):
    devIF = DEV_BROADCAST_DEVICEINTERFACE()
    devIF.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE)
    devIF.dbcc_devicetype = DBT_DEVTYP_DEVICEINTERFACE

    if guid:
        devIF.dbcc_classguid = uuid.UUID(guid).bytes

    return RegisterDeviceNotification(master_window.winfo_id(), ctypes.byref(devIF), 0)

def unregisterDeviceNotification(handle):
    if UnregisterDeviceNotification(handle) == 0:
        raise Exception("Unable to unregister device notification messages")

#Change the following guid to the GUID of the device you want notifications for
GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"


def refresh():
	print("Refresh")
	attached_listbox.delete(*attached_listbox.get_children())
	available_listbox.delete(*available_listbox.get_children())
	
	usb_devices = list_wsl_usb()

	for device in usb_devices:
		if device.Attached:
			attached_listbox.insert('', "end", values=device)
		else:
			if attach_if_pinned(device):
				attached_listbox.insert('', "end", values=device)
			else:
				available_listbox.insert('', "end", values=device)


def attach_if_pinned(device):
	for busid, desc in pinned_profiles:
		if busid and device.BusId.strip() != busid.strip():
			continue
		if desc and device.Description.strip() != desc.strip():
			continue
		attach_wsl_usb(device.BusId)
		available_list_refresh_button.after(1000, refresh)
		return True
	return False
			

# def refresh_attached():
# 	attached_devices = list_attached_usb()
# 	attached_listbox.delete(*attached_listbox.get_children())
# 	for device in attached_devices:
# 		attached_listbox.insert('', "end", values=device)

def attach_wsl():
	# server_ip = remote_ip_input.get()
	selection = available_listbox.selection()
	if not selection:
		print("no selection to attach")
		return
	# print(server_ip)
	print(selection[0])
	print(selection)
	print(available_listbox.item(selection[0]))
	bus_id = available_listbox.item(selection[0])['values'][0].strip()
	description = available_listbox.item(selection[0])['values'][1]
	print(bus_id)
	result = attach_wsl_usb(bus_id)
	print(result.returncode)
	'''if result.returncode == 0:
		attached_devices[bus_id] = {
			'bus_id' : bus_id,
			'port' : len(attached_devices),
			'description' : description
		}
	print(attached_devices)
	'''	
	time.sleep(0.5)
	refresh()

def detach_wsl():
	global attached_listbox
	selection = attached_listbox.selection()
	if not selection:
		print("no selection to detach")
		return # no selected item
	print(selection)
	bus_id = attached_listbox.item(selection[0])['values'][0].strip()

	detach_wsl_usb(bus_id)

	time.sleep(0.5)
	refresh()


Device = namedtuple("Device", "BusId Description Attached")
	
def parse_state(text) -> List[Device]:
	rows = []
	devices = json.loads(text)

	for device in devices['Devices']:
		bus_info = device['BusId']
		if bus_info:
			man_info = device['Description']
			
			attached = device['ClientIPAddress']
			rows.append(Device(
				str(bus_info),
				man_info,
				attached
			))
	return rows


def list_wsl_usb() -> List[Device]:
	result = subprocess.run(["usbipd", "state"], capture_output=True, text=True)
	return parse_state(result.stdout)


def list_attached_usb(devices=None):
	return [d for d in (devices or list_wsl_usb()) if d.Attached]

def attach_wsl_usb(bus_id):
	result = subprocess.run(["usbipd", "wsl", "attach", "--busid="+bus_id], capture_output=True, text=True)
	if "error:" in result.stderr and "administrator privileges" in result.stderr:
		showwarning(title="Administrator Privileges", message="The first time attaching a device to WSL requires elevated privileges; subsequent attaches will succeed with standard user privileges.")
		# result = subprocess.run(['runas', '/noprofile', '/user:Administrator', "usbipd", "wsl", "attach", "--busid="+bus_id], capture_output=True, text=True)
		os.system(r'''Powershell -Command "& { Start-Process \"usbipd\" -ArgumentList @(\"wsl\", \"attach\", \"--busid=%s\") -Verb RunAs } "''' % bus_id)

	
	print(result.stdout)
	print(result.stderr)
	return result

def detach_wsl_usb(bus_id):
	result = subprocess.run(["usbipd", "wsl", "detach", "--busid="+str(bus_id)], capture_output=True, text=True)
	print(result.stdout)
	print(result.stderr)




def auto_attach_wsl():
	global pop
	# server_ip = remote_ip_input.get()
	selection = attached_listbox.selection()
	if not selection:
		print("no selection to create profile for")
		return

	bus_id = attached_listbox.item(selection[0])['values'][0].strip()
	description = attached_listbox.item(selection[0])['values'][1]		

	pop = Toplevel(master_window)
	pop.title("New Auto-Attach Profile")
	pop.geometry("300x120")
	# Create a Label Text
	label = Label(pop, text="Pin by Bus_ID, Description or Both?")
	label.pack(pady=20)
	# Add a Frame
	frame = Frame(pop)
	frame.pack(pady=10)
	# Add Button for making selection
	button1 = Button(frame, text="Bus_ID", command=lambda: auto_attach_wsl_choice(Device(bus_id, None)))
	button1.grid(row=0, column=0, padx=2)
	button2 = Button(frame, text="Description", command=lambda: auto_attach_wsl_choice(None, description))
	button2.grid(row=0, column=1, padx=2)
	button3 = Button(frame, text="Both", command=lambda: auto_attach_wsl_choice(bus_id, description))
	button3.grid(row=0, column=2, padx=2)


# Define a function to implement choice function
def auto_attach_wsl_choice(*option):
	pop.destroy()
	pinned_listbox.insert("", "end", values=option)
	save_auto_attach_profiles()


def delete_profile():
	global pinned_listbox
	selection = pinned_listbox.selection()
	if not selection:
		print("no selection to delete")
		return # no selected item
	print(selection)
	pinned_listbox.delete(selection)
	save_auto_attach_profiles()


def save_auto_attach_profiles():
	global pinned_profiles
	pinned_profiles = [pinned_listbox.item(r)['values'] for r in pinned_listbox.get_children()]
	CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
	CONFIG_FILE.write_text(json.dumps(pinned_profiles))


#class UsbIpGui():

#	def __init__(self):
master_window = Tk()
master_window.wm_title("WSL USB Manager")
master_window.geometry("600x800")

available_control_frame = Frame(master_window)
available_control_frame.grid(column=0, row=0, sticky=W+E, pady=10)

available_list_label = Label(available_control_frame, text="Windows USB Devices")
available_list_refresh_button = Button(available_control_frame, text="Refresh", command=refresh)
available_list_attach_button = Button(available_control_frame, text="Attach Device", command=attach_wsl)


available_listbox = Treeview(master_window, columns=DEVICE_COLUMNS, show="headings")

for i, col in enumerate(DEVICE_COLUMNS):
	available_listbox.heading(col, text=col.title())
	available_listbox.column(col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE)

usb_devices = list_wsl_usb()

remote_devices = [d for d in usb_devices if not d.Attached]
for device in remote_devices:
	available_listbox.insert("", "end", values=device)


available_list_label.grid(column=0, row=0, padx=10)
available_list_refresh_button.grid(column=2, row=0, padx=10)
available_list_attach_button.grid(column=3, row=0, padx=10)
available_listbox.grid(column=0, row=1, sticky=W+E+N+S, padx=10, pady=10)

attached_control_frame = Frame(master_window)
attached_list_label = Label(attached_control_frame, text="Attached Devices")
attached_list_refresh_button = Button(attached_control_frame, text="Refresh", command=refresh)
detach_button = Button(attached_control_frame, text="Detach Device", command=detach_wsl)
auto_attach_button = Button(attached_control_frame, text="Auto-Attach Device", command=auto_attach_wsl)
attached_listbox = Treeview(columns=ATTACHED_COLUMNS, show="headings")

for i, col in enumerate(ATTACHED_COLUMNS):
	attached_listbox.heading(col, text=col.title())
	attached_listbox.column(col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE)

attached_devices = list_attached_usb(usb_devices)
for device in attached_devices:
	attached_listbox.insert("", "end", values=device)

attached_list_label.grid(column=0, row=0, padx=10)
attached_list_refresh_button.grid(column=1, row=0, padx=10)
detach_button.grid(column=2, row=0, padx=10)
auto_attach_button.grid(column=3, row=0, padx=10)

attached_control_frame.grid(column=0, row=2, sticky=E+W, pady=10)
attached_listbox.grid(column=0, row=3, sticky=W+E+N+S, pady=10, padx=10)


pinned_control_frame = Frame(master_window)
pinned_list_label = Label(pinned_control_frame, text="Auto-attached Profiles")
pinned_list_delete_button = Button(pinned_control_frame, text="Delete Profile", command=delete_profile)
pinned_listbox = Treeview(columns=DEVICE_COLUMNS, show="headings")


#setup column names
for i, col in enumerate(DEVICE_COLUMNS):
	pinned_listbox.heading(col, text=col.title())
	#pinned_listbox.column(col, width=tkFont)
	pinned_listbox.column(col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE)


try:
	pinned_profiles = json.loads(CONFIG_FILE.read_text())
	for entry in pinned_profiles:
		pinned_listbox.insert("", "end", values=entry)

	refresh()
except Exception as ex:
	pass

pinned_list_label.grid(column=0, row=0, padx=10)
pinned_list_delete_button.grid(column=3, row=0, padx=10)

pinned_control_frame.grid(column=0, row=4, sticky=E+W, pady=10)
pinned_listbox.grid(column=0, row=5, sticky=W+E+N+S, pady=10, padx=10)


master_window.columnconfigure(0, weight=1)
master_window.rowconfigure(1, weight=1)
master_window.rowconfigure(3, weight=1)
master_window.rowconfigure(5, weight=1)

devNotifyHandle = registerDeviceNotification(guid=GUID_DEVINTERFACE_USB_DEVICE)

WM_DEVICECHANGE = 0x0219
master_window.wm_protocol(0x0219, refresh)
master_window.wm_protocol("WM_DEVICECHANGE", refresh)

# def close():
# 	print("CLOSING")

# master_window.wm_protocol("WM_DELETE_WINDOW", close)

master_window.mainloop()

unregisterDeviceNotification(devNotifyHandle)

