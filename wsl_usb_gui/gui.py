# requires python 3.8+ may work on 3.6, 3.7 definitely broken on <= 3.5 due to subprocess args (text=True)
import asyncio
from tkinter import *
from tkinter.ttk import *
from tkinter import simpledialog
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
ICON_PATH = str(mod_dir / "usb.ico")

DEVICE_COLUMNS = ["bus_id", "description"]
DEVICE_COLUMN_WIDTHS = [50, 50]
ATTACHED_COLUMNS = ["bus_id", "description"]  # , "client"]
ATTACHED_COLUMN_WIDTHS = [20, 80, 20]
USBIPD_PORT = 3240
CONFIG_FILE = Path(appdirs.user_data_dir("wsl-usb-gui", "")) / "config.json"


Device = namedtuple("Device", "BusId Description InstanceId Attached")
Profile = namedtuple("Profile", "BusId Description InstanceId", defaults=(None, None, None))

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
        encoding='UTF-8',
        creationflags=CREATE_NO_WINDOW,
        shell=(isinstance(args, str))
    )


class WslUsbGui:
    def __init__(self):
        self.tkroot = Tk()
        self.tkroot.wm_title("WSL USB Manager")
        self.tkroot.geometry("600x800")
        self.tkroot.iconbitmap(ICON_PATH)

        self.usb_devices = []
        self.pinned_profiles: List[Profile] = []
        self.name_mapping = dict()

        ## TOP SECTION - Available USB Devices
        
        available_control_frame = Frame(self.tkroot)

        available_list_label = Label(available_control_frame, text="Windows USB Devices", font='Helvetica 14 bold')
        refresh_button = Button(available_control_frame, text="Refresh", command=self.refresh)

        available_listbox_frame = Frame(self.tkroot)
        self.available_listbox = Treeview(available_listbox_frame, columns=DEVICE_COLUMNS, show="headings")

        available_listbox_scroll = Scrollbar(available_listbox_frame)
        available_listbox_scroll.configure(command=self.available_listbox.yview)
        self.available_listbox.configure(yscrollcommand=available_listbox_scroll.set)

        available_menu = Menu(self.tkroot, tearoff=0)
        available_menu.add_command(label="Attach to WSL", command=self.attach_wsl)
        available_menu.add_command(label="Auto-Attach Device", command=self.auto_attach_wsl)
        available_menu.add_command(label="Rename Device", command=self.rename_device)
        self.available_listbox.bind("<Button-3>", partial(self.do_listbox_menu, listbox=self.available_listbox, menu=available_menu))

        for i, col in enumerate(DEVICE_COLUMNS):
            self.available_listbox.heading(col, text=col.title())
            self.available_listbox.column(
                col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
            )

        available_list_label.grid(column=0, row=0, padx=10)
        refresh_button.grid(column=2, row=0, sticky=E, padx=10)
        available_control_frame.rowconfigure(0, weight=1)
        available_control_frame.columnconfigure(1, weight=1)

        available_control_frame.grid(column=0, row=0, sticky=W + E, pady=10)
        
        available_listbox_frame.grid(column=0, row=1, sticky=W + E + N + S, pady=10, padx=10)
        available_listbox_frame.rowconfigure(0, weight=1)
        available_listbox_frame.columnconfigure(0, weight=1)
        self.available_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        available_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        ## MIDDLE SECTION - USB devices currently attached
        
        control_frame = Frame(self.tkroot)
        attached_list_label = Label(control_frame, text="WSL USB Devices", font='Helvetica 14 bold')
        

        attach_button = Button(
            control_frame, text="Attach ↓", command=self.attach_wsl
        )

        detach_button = Button(control_frame, text="↑ Detach", command=self.detach_wsl)
        auto_attach_button = Button(
            control_frame, text="Auto-Attach Device", command=self.auto_attach_wsl
        )
        rename_button = Button(
            control_frame, text="Rename", command=self.rename_device
        )
        
        attached_listbox_frame = Frame(self.tkroot)
        self.attached_listbox = Treeview(attached_listbox_frame, columns=ATTACHED_COLUMNS, show="headings")

        attached_listbox_scroll = Scrollbar(attached_listbox_frame)
        attached_listbox_scroll.configure(command=self.attached_listbox.yview)
        self.attached_listbox.configure(yscrollcommand=attached_listbox_scroll.set)

        attached_menu = Menu(self.tkroot, tearoff=0)
        attached_menu.add_command(label="Detach from WSL", command=self.detach_wsl)
        attached_menu.add_command(label="Auto-Attach Device", command=self.auto_attach_wsl)
        attached_menu.add_command(label="Rename Device", command=self.rename_device)
        self.attached_listbox.bind("<Button-3>", partial(self.do_listbox_menu, listbox=self.attached_listbox, menu=attached_menu))

        for i, col in enumerate(ATTACHED_COLUMNS):
            self.attached_listbox.heading(col, text=col.title())
            self.attached_listbox.column(
                col, minwidth=40, width=50, anchor=W if i else CENTER, stretch=TRUE if i else FALSE
            )

        attached_list_label.grid(column=0, row=0, padx=10)

        attach_button.grid(column=1, row=0, padx=5)
        detach_button.grid(column=2, row=0, padx=5)
        auto_attach_button.grid(column=3, row=0, padx=5)
        rename_button.grid(column=4, row=0, padx=5)

        control_frame.grid(column=0, row=2, sticky=E + W, pady=10)

        attached_listbox_frame.grid(column=0, row=3, sticky=W + E + N + S, pady=10, padx=10)
        attached_listbox_frame.rowconfigure(0, weight=1)
        attached_listbox_frame.columnconfigure(0, weight=1)
        self.attached_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        attached_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        ## BOTTOM SECTION - saved profiles for auto-attach
        
        pinned_control_frame = Frame(self.tkroot)
        pinned_list_label = Label(pinned_control_frame, text="Auto-attach Profiles", font='Helvetica 14 bold')
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

        pinned_list_label.grid(column=0, row=0, padx=10)
        pinned_list_delete_button.grid(column=3, row=0, padx=10)

        pinned_control_frame.grid(column=0, row=4, sticky=E + W, pady=10)

        pinned_listbox_frame.grid(column=0, row=5, sticky=W + E + N + S, pady=10, padx=10)
        pinned_listbox_frame.rowconfigure(0, weight=1)
        pinned_listbox_frame.columnconfigure(0, weight=1)
        self.pinned_listbox.grid(column=0, row=0, sticky=W + E + N + S)
        pinned_listbox_scroll.grid(column=1, row=0, sticky=W + N + S)

        # Ensure only one device can be selected at a time
        self.available_listbox.bind("<<TreeviewSelect>>", partial(self.deselect_other_treeviews, treeview=self.available_listbox))
        self.attached_listbox.bind("<<TreeviewSelect>>", partial(self.deselect_other_treeviews, treeview=self.attached_listbox))
        self.pinned_listbox.bind("<<TreeviewSelect>>", partial(self.deselect_other_treeviews, treeview=self.pinned_listbox))

        ## Window Configure
        
        self.tkroot.columnconfigure(0, weight=1)
        self.tkroot.rowconfigure(1, weight=1)
        self.tkroot.rowconfigure(3, weight=1)
        self.tkroot.rowconfigure(5, weight=1)

        self.load_config()
        
        self.refresh()

    @staticmethod
    def create_profile(busid, description, instanceid):
        return Profile(*(None if a == "None" else a for a in (busid, description, instanceid)))
    
    def load_config(self):
        try:
            config = json.loads(CONFIG_FILE.read_text())
            if isinstance(config, list):
                self.pinned_profiles = [self.create_profile(c) for c in config]
            else:
                self.pinned_profiles = [self.create_profile(*c) for c in config["pinned_profiles"]]
                self.name_mapping = config["name_mapping"]

        except Exception as ex:
            pass

    def save_config(self):
        config = dict(
            pinned_profiles=self.pinned_profiles,
            name_mapping=self.name_mapping,
        )
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=4, sort_keys=True))

    
    def parse_state(self, text) -> List[Device]:
        rows = []
        devices = json.loads(text)

        for device in devices["Devices"]:
            bus_info = device["BusId"]
            if bus_info:
                instanceId = device["InstanceId"]
                description = self.name_mapping.get(instanceId, device["Description"])
                attached = device["ClientIPAddress"]
                rows.append(Device(str(bus_info), description, instanceId, attached))
        return rows

    def deselect_other_treeviews(self, *args, treeview):
        if not treeview.selection():
            return
            
        for tv in (
            self.available_listbox,
            self.attached_listbox,
            self.pinned_listbox,
        ):
            if tv is treeview:
                continue
            for i in tv.selection():
                tv.selection_remove(i)

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
            run(r'''Powershell -Command "& { Start-Process \"%s\" -ArgumentList @(\"wsl\", \"attach\", \"--busid=%s\") -Verb RunAs } "'''
                % (USBIPD, bus_id))

        print(result.stdout)
        print(result.stderr)
        return result


    @staticmethod
    def detach_wsl_usb(bus_id):
        result = run([USBIPD, "wsl", "detach", "--busid=" + str(bus_id)])
        print(result.stdout)
        print(result.stderr)


    def update_pinned_listbox(self):
        self.pinned_listbox.delete(*self.pinned_listbox.get_children())
        for profile in self.pinned_profiles:
            busid = str(profile.BusId)
            desc = str(profile.Description or self.lookup_description(profile.InstanceId))
            instanceId = str(profile.InstanceId)
            self.pinned_listbox.insert("", "end", values=(busid, desc, instanceId))

    
    # Define a function to implement choice function
    def auto_attach_wsl_choice(self, profile):
        self.pinned_profiles.append(profile)
        self.save_config()
        self.update_pinned_listbox()

    def remove_pinned_profile(self, busid, description, instanceid):
        profile = self.create_profile(busid, description, instanceid)
        for i, p in enumerate(list(self.pinned_profiles)):
            if ((p.BusId and p.BusId == profile.BusId) or 
               (p.InstanceId and p.InstanceId == profile.InstanceId)):
                self.pinned_profiles.remove(p)

    def delete_profile(self):
        selection = self.pinned_listbox.selection()
        if not selection:
            print("no selection to delete")
            return  # no selected item
        busid, description, instanceid = self.pinned_listbox.item(selection[0])["values"]
        self.pinned_listbox.delete(selection)
        self.remove_pinned_profile(busid, description, instanceid)
        self.save_config()
        
    def get_selection(self):
        rowid = self.available_listbox.selection()
        if rowid:
            return self.available_listbox.item(rowid[0])
        rowid = self.attached_listbox.selection()
        if rowid:
            return self.attached_listbox.item(rowid[0])
        return None
    
    
    def rename_device(self):
        selection = self.get_selection()
        if not selection:
            print("no selection to rename")
            return

        busid, description, *args = selection["values"]
        
        device = [d for d in self.usb_devices if \
            d.BusId == busid and \
            d.Description == description
        ][0]

        instanceId = device.InstanceId

        current = self.name_mapping.get(instanceId, description)

        getnewname = popupTextEntry(self.tkroot, busid, current)
        self.tkroot.wait_window(getnewname.root)
        newname = getnewname.value

        if newname is None:
            # Cancel
            return

        if newname:
            self.name_mapping[instanceId] = newname
        else:
            try:
                self.name_mapping.pop(instanceId)
            except:
                pass
        self.save_config()
        self.refresh()

    async def refresh_task(self, delay=0):
        if delay:
            await asyncio.sleep(delay)

        print("Refresh USB")
        
        self.usb_devices = await asyncio.get_running_loop().run_in_executor(None, self.list_wsl_usb)

        if not self.usb_devices:
            return

        self.attached_listbox.delete(*self.attached_listbox.get_children())
        self.available_listbox.delete(*self.available_listbox.get_children())
        for device in sorted(self.usb_devices, key=lambda d: d.BusId):
            if device.Attached:
                self.attached_listbox.insert("", "end", values=device)
            else:
                if self.attach_if_pinned(device):
                    self.attached_listbox.update()
                    self.attached_listbox.insert("", "end", values=device)
                else:
                    self.available_listbox.insert("", "end", values=device)
        
        self.update_pinned_listbox()

    def refresh(self, delay=0):
        asyncio.get_running_loop().call_soon_threadsafe(asyncio.ensure_future, self.refresh_task(delay))


    def lookup_description(self, instanceId):
        if not instanceId:
            return None

        if instanceId == "None":
            return None

        for device in self.usb_devices:
            if device.InstanceId == instanceId:
                return device.Description
    
    def attach_if_pinned(self, device):
        for busid, desc, instanceId in self.pinned_profiles:
            if (instanceId or busid):
                # Only fallback to description if no other filter set
                desc = None
            
            if busid and device.BusId.strip() != busid.strip():
                continue
            if instanceId and device.InstanceId != instanceId:
                continue
            if desc and device.Description.strip() != desc.strip():
                continue
            self.attach_wsl_usb(device.BusId)
            self.refresh(delay=1000)
            return True
        return False


    def attach_wsl(self):
        selection = self.available_listbox.selection()
        if not selection:
            print("no selection to attach")
            return
        print(self.available_listbox.item(selection[0]))
        bus_id = self.available_listbox.item(selection[0])["values"][0].strip()
        description = self.available_listbox.item(selection[0])["values"][1]
        print(f"Attach {bus_id}")
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
        bus_id, description, instanceId, *_ = self.attached_listbox.item(selection[0])["values"]
        print(f"Detach {bus_id}")

        self.remove_pinned_profile(bus_id, description, instanceId)
        
        self.detach_wsl_usb(bus_id)

        time.sleep(0.5)
        self.refresh()

    def auto_attach_wsl(self):
        global pop
        selection = self.get_selection()
        if not selection:
            print("no selection to create profile for")
            return

        busid, description, instanceId, *args = selection["values"]

        popup = popupAutoAttach(self.tkroot, self, busid, description, instanceId)
        self.tkroot.wait_window(popup.root)
    
        self.refresh()


    def do_listbox_menu(self, event, listbox, menu):
        try:
            listbox.selection_clear()
            iid = listbox.identify_row(event.y)
            if iid:
                listbox.selection_set(iid)
                menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


class popupAutoAttach(simpledialog.SimpleDialog):
    def __init__(self, master, app, bus_id, description, instanceId):
        text = f"Pin the specific device, the physical USB port, or both?"
        super().__init__(master=master, text=text, title="New Auto-Attach Profile", class_=None)
        self.root.iconbitmap(ICON_PATH)
        self.app = app
        self.message["width"] = 250
        self.message["justify"] = 'center'
        f = Frame(self.root)
        f.pack(padx=10, pady=10, expand=True)
        buttonDevice = Button(
            f, text="Device", 
            command=partial(self.choice, app, Profile(None, description, instanceId))
        )
        buttonPort = Button(
            f, text="Port", 
            command=partial(self.choice, app, Profile(bus_id, None, None))
        )
        buttonBoth = Button(
            f, text="Both", 
            command=partial(self.choice, app, Profile(bus_id, description, instanceId))
        )
        buttonDevice.pack(padx=0, pady=0, expand=True, fill='both', side='left')
        buttonPort.pack(padx=10, pady=0, expand=True, fill='both', side='left')
        buttonBoth.pack(padx=0, pady=0, expand=True, fill='both', side='left')
        self.cancel = 0

    def choice(self, app, profile):
        app.auto_attach_wsl_choice(profile)
        self.root.destroy()
        
    def done(self, num):
        self.root.destroy()


class popupTextEntry(simpledialog.SimpleDialog):
    def __init__(self, master, busid=None, name=None):
        text = f"Enter new label for port: {busid}\nOr leave blank to reset to default."
        super().__init__(master=master, text=text, title="Rename", class_=None)
        self.root.iconbitmap(ICON_PATH)
        self.message["width"] = 400
        f = Frame(self.root)
        f.pack(padx=20, pady=10, expand=True)
        self.e=Entry(f)
        self.e.insert(0, name)
        self.e.pack(padx=5, pady=0, side='left', expand=True)
        self.b=Button(f,text='Ok',command=self.return_event)
        self.b.pack(padx=5, pady=0, side='right')
        self.e.focus_set()
        self.cancel = 0

    def return_event(self, event=None):
        self.value = self.e.get()
        self.root.destroy()
    
    def done(self, num):
        self.value = None
        self.root.destroy()


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
