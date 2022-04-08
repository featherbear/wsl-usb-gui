# requires python 3.8+ may work on 3.6, 3.7 definitely broken on <= 3.5 due to subprocess args (text=True)
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
from .usb_monitor import registerDeviceNotification, unregisterDeviceNotification

mod_dir = Path(__file__).parent

DEVICE_COLUMNS = ["bus_id", "description"]
DEVICE_COLUMN_WIDTHS = [50, 50]
ATTACHED_COLUMNS = ["bus_id", "description"]  # , "client"]
ATTACHED_COLUMN_WIDTHS = [20, 80, 20]
USBIPD_PORT = 3240
CONFIG_FILE = Path(appdirs.user_data_dir("wsl-usb-gui", "")) / "config.json"


Device = namedtuple("Device", "BusId Description Attached")
Profile = namedtuple("Profile", "BusId Description")

attached_devices: List[Device] = []
pinned_profiles: List[Profile] = []


def run(args):
    CREATE_NO_WINDOW = 0x08000000
    return subprocess.run(
        args, 
        capture_output=True, 
        text=True, 
        creationflags=CREATE_NO_WINDOW,
        shell=(isinstance(args, str))
    )


def refresh():
    print("Refresh USB")
    attached_listbox.delete(*attached_listbox.get_children())
    available_listbox.delete(*available_listbox.get_children())

    usb_devices = list_wsl_usb()

    for device in usb_devices:
        if device.Attached:
            attached_listbox.insert("", "end", values=device)
        else:
            if attach_if_pinned(device):
                attached_listbox.insert("", "end", values=device)
            else:
                available_listbox.insert("", "end", values=device)


def attach_if_pinned(device):
    for busid, desc in pinned_profiles:
        busid = None if busid == "None" else busid
        desc = None if desc == "None" else desc
        if busid and device.BusId.strip() != busid.strip():
            continue
        if desc and device.Description.strip() != desc.strip():
            continue
        attach_wsl_usb(device.BusId)
        available_list_refresh_button.after(1000, refresh)
        return True
    return False


def attach_wsl():
    selection = available_listbox.selection()
    if not selection:
        print("no selection to attach")
        return
    print(selection[0])
    print(selection)
    print(available_listbox.item(selection[0]))
    bus_id = available_listbox.item(selection[0])["values"][0].strip()
    description = available_listbox.item(selection[0])["values"][1]
    print(bus_id)
    result = attach_wsl_usb(bus_id)
    print(result.returncode)
    """if result.returncode == 0:
		attached_devices[bus_id] = {
			'bus_id' : bus_id,
			'port' : len(attached_devices),
			'description' : description
		}
	print(attached_devices)
	"""
    time.sleep(0.5)
    refresh()


def detach_wsl():
    global attached_listbox
    selection = attached_listbox.selection()
    if not selection:
        print("no selection to detach")
        return  # no selected item
    print(selection)
    bus_id = attached_listbox.item(selection[0])["values"][0].strip()

    detach_wsl_usb(bus_id)

    time.sleep(0.5)
    refresh()


def parse_state(text) -> List[Device]:
    rows = []
    devices = json.loads(text)

    for device in devices["Devices"]:
        bus_info = device["BusId"]
        if bus_info:
            man_info = device["Description"]

            attached = device["ClientIPAddress"]
            rows.append(Device(str(bus_info), man_info, attached))
    return rows


def list_wsl_usb() -> List[Device]:
    result = run(["usbipd", "state"])
    return parse_state(result.stdout)


def list_attached_usb(devices=None) -> List[Device]:
    return [d for d in (devices or list_wsl_usb()) if d.Attached]


def attach_wsl_usb(bus_id):
    result = run(["usbipd", "wsl", "attach", "--busid=" + bus_id])
    if "error:" in result.stderr and "administrator privileges" in result.stderr:
        showwarning(
            title="Administrator Privileges",
            message="The first time attaching a device to WSL requires elevated privileges; subsequent attaches will succeed with standard user privileges.",
        )
        run(r'''Powershell -Command "& { Start-Process \"usbipd\" -ArgumentList @(\"wsl\", \"attach\", \"--busid=%s\") -Verb RunAs } "'''
            % bus_id)

    print(result.stdout)
    print(result.stderr)
    return result


def detach_wsl_usb(bus_id):
    result = run(["usbipd", "wsl", "detach", "--busid=" + str(bus_id)])
    print(result.stdout)
    print(result.stderr)


def auto_attach_wsl():
    global pop
    # server_ip = remote_ip_input.get()
    selection = attached_listbox.selection()
    if not selection:
        print("no selection to create profile for")
        return

    bus_id = attached_listbox.item(selection[0])["values"][0].strip()
    description = attached_listbox.item(selection[0])["values"][1]

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
    button1 = Button(
        frame, text="Bus_ID", command=lambda: auto_attach_wsl_choice(Device(bus_id, None))
    )
    button1.grid(row=0, column=0, padx=2)
    button2 = Button(
        frame, text="Description", command=lambda: auto_attach_wsl_choice(None, description)
    )
    button2.grid(row=0, column=1, padx=2)
    button3 = Button(
        frame, text="Both", command=lambda: auto_attach_wsl_choice(bus_id, description)
    )
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
        return  # no selected item
    print(selection)
    pinned_listbox.delete(selection)
    save_auto_attach_profiles()


def save_auto_attach_profiles():
    global pinned_profiles
    pinned_profiles = [pinned_listbox.item(r)["values"] for r in pinned_listbox.get_children()]
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(pinned_profiles))


def usb_callback(attach):
    print(f"USB attached={attach}")
    refresh()


# class UsbIpGui():

# 	def __init__(self):
master_window = Tk()
master_window.wm_title("WSL USB Manager")
master_window.geometry("600x800")
master_window.iconbitmap(str(mod_dir / "usb.ico"))


available_control_frame = Frame(master_window)
available_control_frame.grid(column=0, row=0, sticky=W + E, pady=10)

available_list_label = Label(available_control_frame, text="Windows USB Devices")
available_list_refresh_button = Button(available_control_frame, text="Refresh", command=refresh)
available_list_attach_button = Button(
    available_control_frame, text="Attach Device", command=attach_wsl
)


available_listbox = Treeview(master_window, columns=DEVICE_COLUMNS, show="headings")

for i, col in enumerate(DEVICE_COLUMNS):
    available_listbox.heading(col, text=col.title())
    available_listbox.column(
        col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
    )

available_list_label.grid(column=0, row=0, padx=10)
available_list_refresh_button.grid(column=2, row=0, padx=10)
available_list_attach_button.grid(column=3, row=0, padx=10)
available_listbox.grid(column=0, row=1, sticky=W + E + N + S, padx=10, pady=10)

attached_control_frame = Frame(master_window)
attached_list_label = Label(attached_control_frame, text="Attached Devices")
attached_list_refresh_button = Button(attached_control_frame, text="Refresh", command=refresh)
detach_button = Button(attached_control_frame, text="Detach Device", command=detach_wsl)
auto_attach_button = Button(
    attached_control_frame, text="Auto-Attach Device", command=auto_attach_wsl
)
attached_listbox = Treeview(columns=ATTACHED_COLUMNS, show="headings")

for i, col in enumerate(ATTACHED_COLUMNS):
    attached_listbox.heading(col, text=col.title())
    attached_listbox.column(
        col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
    )

attached_list_label.grid(column=0, row=0, padx=10)
attached_list_refresh_button.grid(column=1, row=0, padx=10)
detach_button.grid(column=2, row=0, padx=10)
auto_attach_button.grid(column=3, row=0, padx=10)

attached_control_frame.grid(column=0, row=2, sticky=E + W, pady=10)
attached_listbox.grid(column=0, row=3, sticky=W + E + N + S, pady=10, padx=10)


pinned_control_frame = Frame(master_window)
pinned_list_label = Label(pinned_control_frame, text="Auto-attached Profiles")
pinned_list_delete_button = Button(
    pinned_control_frame, text="Delete Profile", command=delete_profile
)
pinned_listbox = Treeview(columns=DEVICE_COLUMNS, show="headings")


# setup column names
for i, col in enumerate(DEVICE_COLUMNS):
    pinned_listbox.heading(col, text=col.title())
    # pinned_listbox.column(col, width=tkFont)
    pinned_listbox.column(
        col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
    )


try:
    pinned_profiles = json.loads(CONFIG_FILE.read_text())
    for entry in pinned_profiles:
        pinned_listbox.insert("", "end", values=entry)

except Exception as ex:
    pass

pinned_list_label.grid(column=0, row=0, padx=10)
pinned_list_delete_button.grid(column=3, row=0, padx=10)

pinned_control_frame.grid(column=0, row=4, sticky=E + W, pady=10)
pinned_listbox.grid(column=0, row=5, sticky=W + E + N + S, pady=10, padx=10)


master_window.columnconfigure(0, weight=1)
master_window.rowconfigure(1, weight=1)
master_window.rowconfigure(3, weight=1)
master_window.rowconfigure(5, weight=1)

refresh()

def main():
    devNotifyHandle = registerDeviceNotification(
        handle=master_window.winfo_id(), callback=usb_callback
    )
    master_window.mainloop()
    unregisterDeviceNotification(devNotifyHandle)


if __name__ == "__main__":
    main()
