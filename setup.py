#!/usr/bin/env python
# Copyright (c) 2022 Andrew Leech <andrew@alelec.net>
#
# SPDX-License-Identifier: MIT
# coding=utf-8
from setuptools import setup, find_packages
from setuptools.command.sdist import sdist as _sdist
import subprocess
import codecs

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


setup(
    name="wsl-usb-gui",
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
            "WSL USB GUI = wsl_usb_gui.gui:main",
        ],
        "console_scripts": [
            "WSL USB GUI (debug) = wsl_usb_gui.gui:main",
        ],
    },
    cmdclass={"sdist": sdist},
    options={
        "app": {
            "formal_name": "WSL USB",
            "bundle": "net.alelec.wsl_usb_gui",
            "icon": "wsl_usb_gui/usb.ico",
        },
    },
)
