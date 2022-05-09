# requires python 3.8+ may work on 3.6, 3.7 definitely broken on <= 3.5 due to subprocess args (text=True)
import asyncio
from tkinter import *
from tkinter.ttk import *
from tkinter.messagebox import showwarning, askokcancel, showinfo
import json
import threading
import subprocess
import time
from collections import namedtuple
from pathlib import Path
from typing import *
import appdirs
from functools import partial
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

app: "WslUsbGui" = None
loop = None

USBIPD_default = Path("C:\\Program Files\\usbipd-win\\usbipd.exe")
if USBIPD_default.exists():
    USBIPD = USBIPD_default
else:
    # try to run from anywhere on path, will try to install later if needed
    USBIPD = "usbipd"


def run(args):
    CREATE_NO_WINDOW = 0x08000000
    return subprocess.run(
        args, 
        capture_output=True, 
        text=True, 
        creationflags=CREATE_NO_WINDOW,
        shell=(isinstance(args, str))
    )


class WslUsbGui:
    def __init__(self):
        self.tkroot = Tk()
        self.tkroot.wm_title("WSL USB Manager")
        self.tkroot.geometry("600x800")
        self.tkroot.iconbitmap(str(mod_dir / "usb.ico"))

        ## TOP SECTION - Available USB Devices
        
        available_control_frame = Frame(self.tkroot)

        available_list_label = Label(available_control_frame, text="Windows USB Devices")
        available_list_attach_button = Button(
            available_control_frame, text="Attach Device", command=self.attach_wsl
        )
        self.available_list_refresh_button = Button(available_control_frame, text="Refresh", command=self.refresh)

        available_listbox_frame = Frame(self.tkroot)
        self.available_listbox = Treeview(available_listbox_frame, columns=DEVICE_COLUMNS, show="headings")

        available_listbox_scroll = Scrollbar(available_listbox_frame)
        available_listbox_scroll.configure(command=self.available_listbox.yview)
        self.available_listbox.configure(yscrollcommand=available_listbox_scroll.set)

        available_menu = Menu(self.tkroot, tearoff=0)
        available_menu.add_command(label="Attach to WSL", command=self.attach_wsl)
        self.available_listbox.bind("<Button-3>", partial(self.do_listbox_menu, listbox=self.available_listbox, menu=available_menu))

        for i, col in enumerate(DEVICE_COLUMNS):
            self.available_listbox.heading(col, text=col.title())
            self.available_listbox.column(
                col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
            )

        available_list_label.grid(column=0, row=0, padx=10)
        available_list_attach_button.grid(column=1, row=0, padx=10)
        self.available_list_refresh_button.grid(column=2, row=0, padx=10)

        available_control_frame.grid(column=0, row=0, sticky=W + E, pady=10)
        
        available_listbox_frame.grid(column=0, row=1, sticky=W + E + N + S, pady=10, padx=10)
        available_listbox_frame.rowconfigure(0, weight=1)
        available_listbox_frame.columnconfigure(0, weight=1)
        self.available_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        available_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        ## MIDDLE SECTION - USB devices currently attached
        
        attached_control_frame = Frame(self.tkroot)
        attached_list_label = Label(attached_control_frame, text="Attached Devices")
        detach_button = Button(attached_control_frame, text="Detach Device", command=self.detach_wsl)
        auto_attach_button = Button(
            attached_control_frame, text="Auto-Attach Device", command=self.auto_attach_wsl
        )
        
        attached_listbox_frame = Frame(self.tkroot)
        self.attached_listbox = Treeview(attached_listbox_frame, columns=ATTACHED_COLUMNS, show="headings")

        attached_listbox_scroll = Scrollbar(attached_listbox_frame)
        attached_listbox_scroll.configure(command=self.attached_listbox.yview)
        self.attached_listbox.configure(yscrollcommand=attached_listbox_scroll.set)

        attached_menu = Menu(self.tkroot, tearoff=0)
        attached_menu.add_command(label="Detach from WSL", command=self.detach_wsl)
        attached_menu.add_command(label="Auto-Attach Device", command=self.auto_attach_wsl)
        self.attached_listbox.bind("<Button-3>", partial(self.do_listbox_menu, listbox=self.attached_listbox, menu=attached_menu))

        for i, col in enumerate(ATTACHED_COLUMNS):
            self.attached_listbox.heading(col, text=col.title())
            self.attached_listbox.column(
                col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
            )

        attached_list_label.grid(column=0, row=0, padx=10)
        detach_button.grid(column=1, row=0, padx=10)
        auto_attach_button.grid(column=2, row=0, padx=10)

        attached_control_frame.grid(column=0, row=2, sticky=E + W, pady=10)

        attached_listbox_frame.grid(column=0, row=3, sticky=W + E + N + S, pady=10, padx=10)
        attached_listbox_frame.rowconfigure(0, weight=1)
        attached_listbox_frame.columnconfigure(0, weight=1)
        self.attached_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        attached_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        ## BOTTOM SECTION - saved profiles for auto-attach
        
        pinned_control_frame = Frame(self.tkroot)
        pinned_list_label = Label(pinned_control_frame, text="Auto-attached Profiles")
        pinned_list_delete_button = Button(
            pinned_control_frame, text="Delete Profile", command=self.delete_profile
        )

        pinned_listbox_frame = Frame(self.tkroot)
        self.pinned_listbox = Treeview(pinned_listbox_frame, columns=DEVICE_COLUMNS, show="headings")

        pinned_listbox_scroll = Scrollbar(pinned_listbox_frame)
        pinned_listbox_scroll.configure(command=self.pinned_listbox.yview)
        self.pinned_listbox.configure(yscrollcommand=pinned_listbox_scroll.set)

        pinned_menu = Menu(self.tkroot, tearoff=0)
        pinned_menu.add_command(label="Delete Profile", command=self.delete_profile)
        self.pinned_listbox.bind("<Button-3>", partial(self.do_listbox_menu, listbox=self.pinned_listbox, menu=pinned_menu))

        # setup column names
        for i, col in enumerate(DEVICE_COLUMNS):
            self.pinned_listbox.heading(col, text=col.title())
            self.pinned_listbox.column(
                col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
            )

        self.pinned_profiles: List[Profile] = []

        try:
            self.pinned_profiles = json.loads(CONFIG_FILE.read_text())
            for entry in self.pinned_profiles:
                self.pinned_listbox.insert("", "end", values=entry)

        except Exception as ex:
            pass

        pinned_list_label.grid(column=0, row=0, padx=10)
        pinned_list_delete_button.grid(column=3, row=0, padx=10)

        pinned_control_frame.grid(column=0, row=4, sticky=E + W, pady=10)

        pinned_listbox_frame.grid(column=0, row=5, sticky=W + E + N + S, pady=10, padx=10)
        pinned_listbox_frame.rowconfigure(0, weight=1)
        pinned_listbox_frame.columnconfigure(0, weight=1)
        self.pinned_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        pinned_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        ## Window Configure
        
        self.tkroot.columnconfigure(0, weight=1)
        self.tkroot.rowconfigure(1, weight=1)
        self.tkroot.rowconfigure(3, weight=1)
        self.tkroot.rowconfigure(5, weight=1)

        self.refresh()

    @staticmethod
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


    def list_wsl_usb(self) -> List[Device]:
        global loop
        try:
            result = run([USBIPD, "state"])
            return self.parse_state(result.stdout)
        except Exception as ex:
            if isinstance(ex, FileNotFoundError):
                loop.call_soon_threadsafe(install_deps)
            return None

    @staticmethod
    def attach_wsl_usb(bus_id):
        result = run([USBIPD, "wsl", "attach", "--busid=" + bus_id])
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


    @staticmethod
    def detach_wsl_usb(bus_id):
        result = run([USBIPD, "wsl", "detach", "--busid=" + str(bus_id)])
        print(result.stdout)
        print(result.stderr)


    # Define a function to implement choice function
    def auto_attach_wsl_choice(self, *option):
        pop.destroy()
        self.pinned_listbox.insert("", "end", values=option)
        self.save_auto_attach_profiles()


    def delete_profile(self):
        selection = self.pinned_listbox.selection()
        if not selection:
            print("no selection to delete")
            return  # no selected item
        print(selection)
        self.pinned_listbox.delete(selection)
        self.save_auto_attach_profiles()


    def save_auto_attach_profiles(self):
        self.pinned_profiles = [self.pinned_listbox.item(r)["values"] for r in self.pinned_listbox.get_children()]
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.pinned_profiles))


    async def refresh_task(self, delay=0):
        if delay:
            await asyncio.sleep(delay)

        print("Refresh USB")
        
        usb_devices = await asyncio.get_running_loop().run_in_executor(None, self.list_wsl_usb)

        if not usb_devices:
            return

        self.attached_listbox.delete(*self.attached_listbox.get_children())
        self.available_listbox.delete(*self.available_listbox.get_children())
        for device in usb_devices:
            if device.Attached:
                self.attached_listbox.insert("", "end", values=device)
            else:
                if self.attach_if_pinned(device):
                    self.attached_listbox.update()
                    self.attached_listbox.insert("", "end", values=device)
                else:
                    self.available_listbox.insert("", "end", values=device)

    def refresh(self, delay=0):
        asyncio.get_running_loop().call_soon_threadsafe(asyncio.ensure_future, self.refresh_task(delay))


    def attach_if_pinned(self, device):
        for busid, desc in self.pinned_profiles:
            busid = None if busid == "None" else busid
            desc = None if desc == "None" else desc
            if busid and device.BusId.strip() != busid.strip():
                continue
            if desc and device.Description.strip() != desc.strip():
                continue
            self.attach_wsl_usb(device.BusId)
            self.available_list_refresh_button.after(1000, self.refresh)
            return True
        return False


    def attach_wsl(self):
        selection = self.available_listbox.selection()
        if not selection:
            print("no selection to attach")
            return
        print(selection[0])
        print(selection)
        print(self.available_listbox.item(selection[0]))
        bus_id = self.available_listbox.item(selection[0])["values"][0].strip()
        description = self.available_listbox.item(selection[0])["values"][1]
        print(bus_id)
        result = self.attach_wsl_usb(bus_id)
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
        self.refresh()

    def detach_wsl(self):
        selection = self.attached_listbox.selection()
        if not selection:
            print("no selection to detach")
            return  # no selected item
        print(selection)
        bus_id = self.attached_listbox.item(selection[0])["values"][0].strip()

        self.detach_wsl_usb(bus_id)

        time.sleep(0.5)
        self.refresh()

    def auto_attach_wsl(self):
        global pop
        # server_ip = remote_ip_input.get()
        selection = self.attached_listbox.selection()
        if not selection:
            print("no selection to create profile for")
            return

        bus_id = self.attached_listbox.item(selection[0])["values"][0].strip()
        description = self.attached_listbox.item(selection[0])["values"][1]

        pop = Toplevel(self.tkroot)
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
            frame, text="Bus_ID", command=lambda: self.auto_attach_wsl_choice(Device(bus_id, None))
        )
        button1.grid(row=0, column=0, padx=2)
        button2 = Button(
            frame, text="Description", command=lambda: self.auto_attach_wsl_choice(None, description)
        )
        button2.grid(row=0, column=1, padx=2)
        button3 = Button(
            frame, text="Both", command=lambda: self.auto_attach_wsl_choice(bus_id, description)
        )
        button3.grid(row=0, column=2, padx=2)




    def do_listbox_menu(self, event, listbox, menu):
        try:
            listbox.selection_clear()
            iid = listbox.identify_row(event.y)
            if iid:
                listbox.selection_set(iid)
                menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


def usb_callback(attach):
    print(f"USB attached={attach}")
    if app:
        app.refresh(0.5)


def install_deps():
    global USBIPD
    if askokcancel("Install Dependencies", "Some of the dependencies are missing, install them now?\nNote: All WSL instances may need to be restarted."):
        from .install import install_task
        rsp = install_task()
        showinfo("Finished", "Finished Installation")
        if rsp:
            USBIPD = USBIPD_default
            app.refresh()


async def amain():
    global app
    app = WslUsbGui()

    devNotifyHandle = registerDeviceNotification(
        handle=app.tkroot.winfo_id(), callback=usb_callback
    )
    while True:
        try:
            app.tkroot.update()
            await asyncio.sleep(0.001)
        except:
            break

    unregisterDeviceNotification(devNotifyHandle)


def main():
    global loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(amain())

if __name__ == "__main__":
    main()
