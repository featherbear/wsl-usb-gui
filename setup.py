#!/usr/bin/env python
# Copyright (c) 2022 Andrew Leech <andrew@alelec.net>
#
# SPDX-License-Identifier: MIT
# coding=utf-8
import os
import sys
import time
from setuptools import setup, find_packages
from setuptools.command.sdist import sdist as _sdist
import subprocess
from pathlib import Path
import http.server
import socketserver
import threading

from wsl_usb_gui.version import version_scheme


class sdist(_sdist):
    def run(self):
        try:
            subprocess.check_call("make")
        except subprocess.CalledProcessError as e:
            raise SystemExit(e)
        _sdist.run(self)


with open("README.md") as f:
    long_description = f.read()


root = Path(__file__).parent
pyproject = Path(root / "pyproject.toml")
pyproject_disabled = Path(root / "__pyproject.toml")
renamed = False

if pyproject.exists():
    pyproject.rename(pyproject_disabled)
    os.system(f"git update-index --assume-unchanged {pyproject}")
    renamed = True



if len(sys.argv) > 1 and sys.argv[1] == "windows":
    # Briefcase expects to download the base python embed zip from a http url.
    # As we needed to modify this package to include tkinter, we need to provide 
    # our own download url to the local zip in this folder.
    file_server_port = 0

    def start_file_server():
        os.chdir(Path(__file__).parent)

        Handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
            global file_server_port
            file_server_port = httpd.socket.getsockname()[1]
            # print("serving at port", file_server_port)
            httpd.serve_forever()

    daemon = threading.Thread(name='daemon_server',
                            target=start_file_server)
    daemon.setDaemon(True) # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()

    while file_server_port == 0:
        time.sleep(0.25)

    sys.argv.extend(["--support-pkg", f"http://127.0.0.1:{file_server_port}/python-3.9.2-embed-amd64-tkinter.zip"])


try:
    setup(
        name="wsl_usb_gui",
        author="Andrew Leech",
        author_email="andrew@alelec.net",
        url="https://gitlab.com/alelec/wsl-usb-gui",
        description="WSL USB Management Tool.",
        long_description=long_description,
        packages=find_packages(),
        include_package_data=True,
        use_scm_version=version_scheme,
        use_windows_entry_exe=True,
        setup_requires=["setuptools-scm", "windows-entry-exe"],
        install_requires=["setuptools-scm", "appdirs"],
        package_data={
            "": ["*.txt", "*.rst", "*.md", "*.ico"],
        },
        entry_points={
            "gui_scripts": [
                "WSL USB=wsl_usb_gui.gui:main",
            ],
            #"console_scripts": [
            #   "WSL USB debug=wsl_usb_gui.gui:main",
            #],
        },
        cmdclass={"sdist": sdist},
        options={
            "app": {
                "formal_name": "WSL USB",
                "bundle": "net.alelec.wsl-usb-gui",
                "icon": "wsl_usb_gui/usb",
            },
        },
    )
finally:
    if renamed and pyproject_disabled.exists():
        pyproject_disabled.rename(pyproject)
