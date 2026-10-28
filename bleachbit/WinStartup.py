# SPDX-License-Identifier: GPL-3.0-or-later
# Startup manager logic for the CC-style tools page. GTK-free.
#
# Design notes:
# - Registry entries live under the standard Run/RunOnce keys of both
#   registry views (64-bit and WOW64) for HKLM and HKCU.
# - "Disable" moves the value into a backup key under HKCU owned by this
#   application; "enable" restores it. Deleting from HKLM needs admin and
#   failures are surfaced, never swallowed.
# - Startup-folder shortcuts are disabled by moving the .lnk into a
#   BleachBitCC "Disabled Startup" folder next to the original.

import os
import winreg

BACKUP_KEY = r"Software\BleachBitCC\StartupBackup"
DISABLED_FOLDER_NAME = "BleachBitCC Disabled Startup"

_RUN_LOCATIONS = (
    # (hive, subkey, view, is_folder_backup_possible, label)
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     0, False, "HKCU\\...\\Run"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
     0, False, "HKCU\\...\\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     winreg.KEY_WOW64_64KEY, False, "HKLM(64)\\...\\Run"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     winreg.KEY_WOW64_32KEY, False, "HKLM(32)\\...\\Run"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
     winreg.KEY_WOW64_64KEY, False, "HKLM(64)\\...\\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
     winreg.KEY_WOW64_32KEY, False, "HKLM(32)\\...\\RunOnce"),
)


class StartupEntry:
    """One auto-start item.

    kind: 'registry' or 'folder'
    location: which Run key or startup folder the entry belongs to
    name: value name / file name shown to the user
    command: command line / file path
    state: 'enabled' or 'disabled'
    """

    __slots__ = ("kind", "location", "name", "command", "state", "hive",
                 "subkey", "view", "path")

    def __init__(self, kind, location, name, command, state,
                 hive=None, subkey=None, view=0, path=None):
        self.kind = kind
        self.location = location
        self.name = name
        self.command = command
        self.state = state
        self.hive = hive
        self.subkey = subkey
        self.view = view
        self.path = path

    def __repr__(self):
        return "<StartupEntry %s %s [%s]>" % (self.kind, self.name,
                                              self.state)


def _iter_values(key):
    """Yield (name, value) pairs of an open registry key."""
    index = 0
    while True:
        try:
            name, value, _type = winreg.EnumValue(key, index)
        except OSError:
            return
        yield name, value
        index += 1


def _hive_name(hive):
    return "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"


def list_startup_entries():
    """Enumerate all auto-start entries (registry + startup folders)."""
    entries = []
    for hive, subkey, view, _f, label in _RUN_LOCATIONS:
        try:
            with winreg.OpenKey(hive, subkey, 0,
                                winreg.KEY_READ | view) as key:
                values = list(_iter_values(key))
        except OSError:
            continue
        for name, command in values:
            disabled = _is_backed_up(hive, subkey, view, name)
            entries.append(StartupEntry(
                kind="registry", location=label, name=name,
                command=str(command),
                state="disabled" if disabled else "enabled",
                hive=hive, subkey=subkey, view=view))
    entries.extend(_list_backup_entries())
    entries.extend(_list_startup_folder(
        os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
        "用户启动文件夹"))
    entries.extend(_list_startup_folder(
        os.path.expandvars(
            r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"),
        "公共启动文件夹"))
    return entries


def _list_backup_entries():
    """Enumerate disabled entries living in the backup key."""
    labels = {(h, s, v): lbl for h, s, v, _f, lbl in _RUN_LOCATIONS}
    entries = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY, 0,
                            winreg.KEY_READ) as bkey:
            values = list(_iter_values(bkey))
    except OSError:
        return entries
    for name, value in values:
        if "\\" not in name:
            continue
        location_part, _, value_name = name.rpartition("\\")
        try:
            hive_s, subkey, view_s = location_part.split("|")
            view = int(view_s)
        except ValueError:
            continue
        hive = winreg.HKEY_CURRENT_USER if hive_s == "HKCU" \
            else winreg.HKEY_LOCAL_MACHINE
        label = labels.get((hive, subkey, view),
                           "%s\\%s" % (hive_s, subkey))
        entries.append(StartupEntry(
            kind="registry", location=label, name=value_name,
            command=str(value), state="disabled",
            hive=hive, subkey=subkey, view=view))
    return entries


def _list_startup_folder(folder, label):
    disabled_dir = os.path.join(os.path.dirname(folder.rstrip("\\/")),
                                DISABLED_FOLDER_NAME)
    entries = []
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            entries.append(StartupEntry(
                kind="folder", location=label, name=fn,
                command=os.path.join(folder, fn), state="enabled",
                path=folder))
    if os.path.isdir(disabled_dir):
        for fn in sorted(os.listdir(disabled_dir)):
            entries.append(StartupEntry(
                kind="folder", location=label, name=fn,
                command=os.path.join(disabled_dir, fn), state="disabled",
                path=disabled_dir))
    return entries


def _backup_value_name(hive, subkey, view):
    return "%s|%s|%d" % (_hive_name(hive), subkey, view)


def _is_backed_up(hive, subkey, view, name):
    """True when `name` for this location sits in the backup key."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY, 0,
                            winreg.KEY_READ) as bkey:
            data, _type = winreg.QueryValueEx(
                bkey, "%s\\%s" % (_backup_value_name(hive, subkey, view),
                                  name))
            return data is not None
    except OSError:
        return False


def disable_entry(entry):
    """Disable a registry auto-start entry (backup + remove).

    Folder entries are disabled by moving the shortcut. Returns None on
    success or a human-readable error string.
    """
    if entry.kind == "folder":
        return _disable_folder_entry(entry)
    try:
        with winreg.OpenKey(entry.hive, entry.subkey, 0,
                            winreg.KEY_READ | entry.view) as key:
            value, vtype = winreg.QueryValueEx(key, entry.name)
    except OSError as e:
        return "读取注册表失败: %s" % e
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY) as bkey:
            winreg.SetValueEx(
                bkey,
                "%s\\%s" % (_backup_value_name(entry.hive, entry.subkey,
                                              entry.view), entry.name),
                0, vtype, value)
        with winreg.OpenKey(entry.hive, entry.subkey, 0,
                            winreg.KEY_SET_VALUE | entry.view) as key:
            winreg.DeleteValue(key, entry.name)
    except PermissionError:
        return "没有管理员权限，无法修改 %s" % _hive_name(entry.hive)
    except OSError as e:
        return "修改注册表失败: %s" % e
    return None


def enable_entry(entry):
    """Restore a previously disabled registry entry.

    Returns None on success or an error string.
    """
    if entry.kind == "folder":
        return _enable_folder_entry(entry)
    backup_name = "%s\\%s" % (_backup_value_name(entry.hive, entry.subkey,
                                                entry.view), entry.name)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY, 0,
                            winreg.KEY_READ) as bkey:
            value, vtype = winreg.QueryValueEx(bkey, backup_name)
        with winreg.OpenKey(entry.hive, entry.subkey, 0,
                            winreg.KEY_SET_VALUE | entry.view) as key:
            winreg.SetValueEx(key, entry.name, 0, vtype, value)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY, 0,
                            winreg.KEY_SET_VALUE) as bkey:
            winreg.DeleteValue(bkey, backup_name)
    except PermissionError:
        return "没有管理员权限，无法修改 %s" % _hive_name(entry.hive)
    except FileNotFoundError:
        return "备份记录不存在，无法恢复"
    except OSError as e:
        return "恢复注册表失败: %s" % e
    return None


def delete_entry(entry):
    """Delete an entry permanently. Returns None or an error string."""
    if entry.kind == "folder":
        try:
            os.remove(entry.command)
        except OSError as e:
            return "删除文件失败: %s" % e
        return None
    if entry.state == "disabled":
        # disabled entries live in the backup key
        backup_name = "%s\\%s" % (_backup_value_name(entry.hive,
                                                    entry.subkey,
                                                    entry.view), entry.name)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BACKUP_KEY, 0,
                                winreg.KEY_SET_VALUE) as bkey:
                winreg.DeleteValue(bkey, backup_name)
        except PermissionError:
            return "没有管理员权限"
        except FileNotFoundError:
            return "条目已不存在"
        except OSError as e:
            return "删除备份记录失败: %s" % e
        return None
    try:
        with winreg.OpenKey(entry.hive, entry.subkey, 0,
                            winreg.KEY_SET_VALUE | entry.view) as key:
            winreg.DeleteValue(key, entry.name)
    except PermissionError:
        return "没有管理员权限，无法修改 %s" % _hive_name(entry.hive)
    except FileNotFoundError:
        return "条目已不存在"
    except OSError as e:
        return "删除注册表值失败: %s" % e
    return None


def _disable_folder_entry(entry):
    target = os.path.join(os.path.dirname(entry.path.rstrip("\\/")),
                          DISABLED_FOLDER_NAME)
    try:
        os.makedirs(target, exist_ok=True)
        new_path = os.path.join(target, entry.name)
        if os.path.exists(new_path):
            return "目标位置已存在同名文件"
        os.rename(entry.command, new_path)
    except OSError as e:
        return "移动文件失败: %s" % e
    return None


def _enable_folder_entry(entry):
    # find the original folder from the label mapping
    for folder in (os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
            os.path.expandvars(
                r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"
                r"\Startup")):
        if os.path.dirname(entry.command.rstrip("\\/")).lower() != \
                os.path.join(os.path.dirname(folder.rstrip("\\/")),
                             DISABLED_FOLDER_NAME).lower():
            continue
        new_path = os.path.join(folder, entry.name)
        try:
            os.rename(entry.command, new_path)
        except OSError as e:
            return "移动文件失败: %s" % e
        return None
    return "找不到原始启动文件夹"
