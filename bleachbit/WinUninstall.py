# SPDX-License-Identifier: GPL-3.0-or-later
# Installed-programs enumeration for the CC-style tools page. GTK-free.
#
# Read-only scanning of the standard Uninstall registry keys. Launching an
# uninstaller runs the command recorded by the vendor in the registry.

import os
import subprocess
import winreg

_UNINSTALL_LOCATIONS = (
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_32KEY),
)


class InstalledProgram:
    __slots__ = ("name", "version", "publisher", "install_location",
                 "uninstall_string", "quiet_string", "key_path",
                 "estimated_size_kb")

    def __init__(self, name, version, publisher, install_location,
                 uninstall_string, quiet_string, key_path,
                 estimated_size_kb=None):
        self.name = name
        self.version = version
        self.publisher = publisher
        self.install_location = install_location
        self.uninstall_string = uninstall_string
        self.quiet_string = quiet_string
        self.key_path = key_path
        self.estimated_size_kb = estimated_size_kb

    def __repr__(self):
        return "<InstalledProgram %s %s>" % (self.name, self.version or "")


def _hive_name(hive):
    return "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"


def _iter_subkeys(key):
    index = 0
    while True:
        try:
            subkey_name = winreg.EnumKey(key, index)
        except OSError:
            return
        yield subkey_name
        index += 1


def list_installed_programs():
    """Enumerate installed programs from the Uninstall registry keys."""
    programs = []
    for hive, subkey, view in _UNINSTALL_LOCATIONS:
        try:
            with winreg.OpenKey(hive, subkey, 0,
                                winreg.KEY_READ | view) as root:
                subkeys = list(_iter_subkeys(root))
        except OSError:
            continue
        for sk_name in subkeys:
            full = "%s\\%s" % (subkey, sk_name)
            try:
                with winreg.OpenKey(hive, full, 0,
                                    winreg.KEY_READ | view) as key:
                    def _get(name):
                        try:
                            value, _t = winreg.QueryValueEx(key, name)
                            return value
                        except OSError:
                            return None
                    display_name = _get("DisplayName")
                    if not display_name:
                        continue
                    system_component = _get("SystemComponent")
                    if system_component == 1:
                        continue
                    estimated = _get("EstimatedSize")
                    programs.append(InstalledProgram(
                        name=str(display_name),
                        version=_get("DisplayVersion"),
                        publisher=_get("Publisher"),
                        install_location=_get("InstallLocation"),
                        uninstall_string=_get("UninstallString"),
                        quiet_string=_get("QuietUninstallString"),
                        key_path="%s\\%s" % (_hive_name(hive), full),
                        estimated_size_kb=estimated if isinstance(
                            estimated, int) else None,
                    ))
            except OSError:
                continue
    programs.sort(key=lambda p: p.name.lower())
    return programs


def launch_uninstaller(program):
    """Run the vendor uninstaller for `program`.

    Prefers the quiet uninstall string when present. Returns None on
    success (process started) or an error string.
    """
    command = program.quiet_string or program.uninstall_string
    if not command:
        return "该程序没有记录卸载命令"
    try:
        subprocess.Popen(command, shell=True,
                         cwd=program.install_location or None,
                         creationflags=subprocess.DETACHED_PROCESS
                         if hasattr(subprocess, "DETACHED_PROCESS") else 0)
    except OSError as e:
        return "启动卸载程序失败: %s" % e
    return None
