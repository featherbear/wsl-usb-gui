import sys
from pathlib import Path

app_packages = Path(__file__).parent / ".." / ".." / "app_packages"
sys.path.extend([str(app_packages.resolve())])

import appdirs
import subprocess
import tkinter as tk
from tkinter.messagebox import askokcancel
import logging

install_log = Path(appdirs.user_data_dir("wsl-usb-gui", "")) / "install.log"
print("Logging to", install_log)
logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(message)s", filename=install_log, encoding='utf-8', level=logging.DEBUG)

logging.info("Running post-install script")

def run(args, show=False):
    CREATE_NO_WINDOW = 0x08000000
    return subprocess.run(
        args,
        capture_output=True, 
        creationflags=0 if show else CREATE_NO_WINDOW,
        shell=(isinstance(args, str))
    )

def msgbox_ok_cancel(title, message):
    root = tk.Tk()
    root.overrideredirect(1)
    root.withdraw()
    ret = askokcancel(title, message)
    root.destroy()
    return ret

# Check WSL Version
def check_wsl_version():
    try:
        wsl_installs_ret = run("wsl --list -v").stdout
        wsl_installs = wsl_installs_ret.decode().replace("\x00", "").split("\n")
        iname = wsl_installs[0].find("NAME")
        istate = wsl_installs[0].find("STATE")
        iversion = wsl_installs[0].find("VERSION")
        if -1 in (iname, istate, iversion):
            logging.error("Warning: Cannot check WSL2 version")
        else:
            for row in wsl_installs[1:]:
                if row.strip().startswith("*"):
                    name = row[iname:istate].strip()
                    version = row[iversion:].strip()
                    if version != "2":
                        logging.warning(f"Default WSL ({name}) needs updating to version 2")
                        update_wsl_version(name)
                    else:
                        logging.info(f"Default WSL ({name}) already version 2")
                    break
    except Exception as ex:
        logging.exception(ex)
        rsp = msgbox_ok_cancel(
            title="Error checking WSL version",
            message=f"An unexpected error occurred while checking WSL version, continue anyway?",
        )
        if not rsp:
            raise SystemExit(ex)

def update_wsl_version(name):
    rsp = msgbox_ok_cancel(
            title="WSL convert to version 2?",
            message=f"Default WSL ({name}) needs updating to version 2, do this now?",
        )
    if rsp:
        run(f'wsl --set-version "{name}" 2', show=True)


def check_kernel_version():
    try:
        version = run(["C:\Windows\System32\wsl.exe", "--", "/bin/uname", "-r"]).stdout.decode().strip()
        logging.info(f"WSL2 Kernel: {version}")
        number = version.split("-")[0]
        number_tuple = tuple((int(n) for n in number.split(".")))
        if number_tuple < (5,10,60,1):
            logging.warning("Kernel needs updating")
            run("wsl --shutdown")
            run("wsl --update", show=True)
    
    except Exception as ex:
        logging.exception(ex)
        rsp = msgbox_ok_cancel(
            title="Error checking WSL kernel version",
            message=f"An unexpected error occurred while checking WSL kernel version, continue anyway?",
        )
        if not rsp:
            raise SystemExit(ex)


def install_client():
    try:
        rsp = run(f'bash -c "sudo apt install linux-tools-5.4.0-77-generic hwdata; sudo update-alternatives --install /usr/local/bin/usbip usbip /usr/lib/linux-tools/*/usbip 20"', show=True)
        logging.info("Installing WSL client tools:")
        logging.info(rsp.stdout.decode())
    except Exception as ex:
        logging.exception(ex)
        rsp = msgbox_ok_cancel(
            title="Error installing linux tools",
            message=f"An unexpected error occurred while installing linux tools, continue anyway?",
        )
        if not rsp:
            raise SystemExit(ex)

def install_server():
    try:
        rsp = run(r'''Powershell -Command "& { Start-Process \"winget\" -ArgumentList @(\"install\", \"--interactive\", \"--exact\", \"dorssel.usbipd-win\") -Verb RunAs } "''', show=True)
        logging.info(rsp.stdout.decode())
    except Exception as ex:
        logging.exception(ex)
        rsp = msgbox_ok_cancel(
            title="Error installing usbipd-win",
            message=f"An unexpected error occurred while installing windows server, continue anyway?",
        )
        if not rsp:
            raise SystemExit(ex)


check_wsl_version()
check_kernel_version()
install_client()
install_server()

logging.info("Finished")
