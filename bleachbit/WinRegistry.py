# SPDX-License-Identifier: GPL-3.0-or-later
# Conservative registry cleaner logic. GTK-free.
#
# Safety model (per project constraints):
# - The feature is opt-in (options key `registry_cleaner_enabled`).
# - Every pending deletion is exported to a .reg backup file BEFORE any
#   write; the file can be re-imported with `reg import`.
# - HKCU entries are fixed directly. HKLM entries are scanned and backed
#   up, but fixing them requires admin and is attempted with the error
#   reported per item on failure.

import os
import winreg

MUI_CACHE_KEY = (winreg.HKEY_CURRENT_USER,
                 r"Software\Classes\Local Settings\Software\Microsoft"
                 r"\Windows\Shell\MuiCache")
APP_PATHS_LOCATIONS = (
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
)
SHARED_DLLS_KEY = (winreg.HKEY_LOCAL_MACHINE,
                   r"Software\Microsoft\Windows\CurrentVersion"
                   r"\SharedDLLs")
UNINSTALL_LOCATIONS = (
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
     winreg.KEY_WOW64_32KEY),
)

_REG_TYPE_NAMES = {
    winreg.REG_SZ: "REG_SZ",
    winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
    winreg.REG_BINARY: "REG_BINARY",
    winreg.REG_DWORD: "REG_DWORD",
    winreg.REG_DWORD_BIG_ENDIAN: "REG_DWORD_BIG_ENDIAN",
    winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
    winreg.REG_QWORD: "REG_QWORD",
}


class RegistryIssue:
    """One fixable finding.

    kind: 'value' (delete a value) or 'key' (delete a whole subkey)
    """

    __slots__ = ("category", "hive", "subkey", "view", "name", "detail",
                 "kind")

    def __init__(self, category, hive, subkey, view, name, detail,
                 kind="value"):
        self.category = category
        self.hive = hive
        self.subkey = subkey
        self.view = view
        self.name = name
        self.detail = detail
        self.kind = kind

    @property
    def hive_name(self):
        # full names required by the .reg file format
        return "HKEY_CURRENT_USER" \
            if self.hive == winreg.HKEY_CURRENT_USER else "HKEY_LOCAL_MACHINE"

    @property
    def full_path(self):
        base = "%s\\%s" % (self.hive_name, self.subkey)
        return base if self.kind == "key" else "%s\\%s" % (base, self.name)

    def __repr__(self):
        return "<RegistryIssue %s>" % self.full_path


def _key_exists_file(path):
    if not path:
        return True  # unknown -> never flag
    return os.path.isfile(path) or os.path.isdir(path)


def _expand(value):
    if isinstance(value, str) and "%" in value:
        try:
            return os.path.expandvars(value)
        except Exception:
            return value
    return value


def _iter_values(key):
    index = 0
    while True:
        try:
            yield winreg.EnumValue(key, index)
        except OSError:
            return
        index += 1


def _iter_subkeys(key):
    index = 0
    while True:
        try:
            yield winreg.EnumKey(key, index)
        except OSError:
            return
        index += 1


def scan_registry(progress_cb=None, should_continue=None):
    """Scan for stale registry entries. Returns [RegistryIssue, ...]."""
    if progress_cb is None:
        progress_cb = lambda *a: None
    if should_continue is None:
        should_continue = lambda: True
    issues = []
    if not is_registry_cleaner_enabled():
        return issues

    # 1. MuiCache: references to binaries that no longer exist
    hive, subkey = MUI_CACHE_KEY
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
            for name, value, _t in list(_iter_values(key)):
                if not should_continue():
                    return issues
                # value names look like "C:\\path\\app.exe.FriendlyAppName"
                path = name.rsplit(".", 1)[0] if "." in name else name
                if path.lower().endswith((".exe", ".dll")) and \
                        not _key_exists_file(_expand(path)):
                    issues.append(RegistryIssue(
                        "MUI 缓存", hive, subkey, 0, name,
                        "指向不存在的文件: %s" % path))
    except OSError:
        pass
    progress_cb(1)

    # 2. App Paths: default value pointing to a missing binary
    for hive, subkey in APP_PATHS_LOCATIONS:
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as root:
                subkeys = list(_iter_subkeys(root))
        except OSError:
            continue
        for sk in subkeys:
            if not should_continue():
                return issues
            full = "%s\\%s" % (subkey, sk)
            try:
                with winreg.OpenKey(hive, full, 0, winreg.KEY_READ) as key:
                    try:
                        default, _t = winreg.QueryValueEx(key, "")
                    except OSError:
                        continue
                    target = _expand(default)
                    if isinstance(target, str) and target and \
                            not _key_exists_file(target):
                        issues.append(RegistryIssue(
                            "应用路径", hive, full, 0, "",
                            "默认值指向不存在的文件: %s" % target,
                            kind="key"))
            except OSError:
                continue
        progress_cb(2)

    # 3. SharedDLLs: reference counters for missing files (report only
    #    unless admin; fixing happens through the same value delete)
    hive, subkey = SHARED_DLLS_KEY
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
            for name, _value, _t in list(_iter_values(key)):
                if not should_continue():
                    return issues
                if name and not _key_exists_file(_expand(name)):
                    issues.append(RegistryIssue(
                        "共享 DLL", hive, subkey, 0, name,
                        "文件不存在: %s" % name))
    except OSError:
        pass
    progress_cb(3)

    # 4. Uninstall leftovers: install location missing on disk
    for hive, subkey, view in UNINSTALL_LOCATIONS:
        try:
            with winreg.OpenKey(hive, subkey, 0,
                                winreg.KEY_READ | view) as root:
                subkeys = list(_iter_subkeys(root))
        except OSError:
            continue
        for sk in subkeys:
            if not should_continue():
                return issues
            full = "%s\\%s" % (subkey, sk)
            try:
                with winreg.OpenKey(hive, full, 0,
                                    winreg.KEY_READ | view) as key:
                    names = {n for (n, _v, _t) in _iter_values(key)}
                    install_location = None
                    for candidate in ("InstallLocation",
                                      "UninstallString"):
                        if candidate in names:
                            value, _t = winreg.QueryValueEx(key, candidate)
                            install_location = _expand(value)
                            if candidate == "InstallLocation" and \
                                    install_location:
                                break
                    if not install_location:
                        continue
                    # UninstallString embeds arguments; take the exe part
                    probe = install_location.strip().strip('"')
                    probe = probe.split(" /", 1)[0].strip()
                    if not _key_exists_file(probe):
                        continue
                    issues.append(RegistryIssue(
                        "卸载残留", hive, full, view, "",
                        "安装位置不存在: %s" % probe, kind="key"))
            except OSError:
                continue
    progress_cb(4)
    return issues


def is_registry_cleaner_enabled():
    """The feature is opt-in; default off."""
    from bleachbit.Options import options
    return options.get('registry_cleaner_enabled') is True


def _reg_escape(s):
    return s.replace("\\", "\\\\")


def write_reg_backup(issues, backup_path):
    """Export everything needed to undo `issues` into a .reg file.

    Returns the backup path. Raises on I/O errors.
    """
    lines = ["Windows Registry Editor Version 5.00", ""]
    written = set()
    for issue in issues:
        full = "%s\\%s" % (issue.hive_name, issue.subkey)
        if issue.kind == "key" or full not in written:
            lines.append("[%s]" % _reg_escape(full))
            written.add(full)
        if issue.kind == "value" and issue.name:
            try:
                with winreg.OpenKey(issue.hive, issue.subkey, 0,
                                    winreg.KEY_READ | issue.view) as key:
                    value, vtype = winreg.QueryValueEx(key, issue.name)
            except OSError:
                continue
            lines.append(_format_value_line(issue.name, value, vtype))
    with open(backup_path, "w", encoding="utf-16-le", newline="") as f:
        # .reg files with UTF-16 need a BOM
        f.write("\ufeff")
        f.write("\r\n".join(lines) + "\r\n")
    return backup_path


def _format_value_line(name, value, vtype):
    typename = _REG_TYPE_NAMES.get(vtype)
    if typename == "REG_SZ":
        return '"%s"=hex(00000001):%s' % (
            name, ",".join("%02x" % b for b in
                           (value + "\0").encode("utf-16-le")))
    if typename == "REG_EXPAND_SZ":
        return '"%s"=hex(00000002):%s' % (
            name, ",".join("%02x" % b for b in
                           (value + "\0").encode("utf-16-le")))
    if vtype == winreg.REG_DWORD:
        return '"%s"=dword:%08x' % (name, value & 0xFFFFFFFF)
    if vtype == winreg.REG_QWORD:
        return '"%s"=hex(b):%s' % (
            name, ",".join("%02x" % b for b in
                           value.to_bytes(8, "little")))
    # REG_BINARY / REG_MULTI_SZ and anything else: raw little-endian hex
    if isinstance(value, str):
        raw = value.encode("utf-16-le") + b"\0\0"
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = str(value).encode("utf-16-le") + b"\0\0"
    return '"%s"=hex:%s' % (
        name, ",".join("%02x" % b for b in raw))


def fix_issue(issue):
    """Apply one fix. Returns None on success or an error string."""
    try:
        if issue.kind == "key":
            with winreg.OpenKey(issue.hive, issue.subkey.rsplit("\\", 1)[0],
                                0, winreg.KEY_SET_VALUE | issue.view) as key:
                winreg.DeleteKey(key, issue.subkey.rsplit("\\", 1)[-1])
        else:
            with winreg.OpenKey(issue.hive, issue.subkey, 0,
                                winreg.KEY_SET_VALUE | issue.view) as key:
                winreg.DeleteValue(key, issue.name)
    except PermissionError:
        return "没有管理员权限，无法修改 %s" % issue.hive_name
    except FileNotFoundError:
        return None  # already gone -> counts as fixed
    except OSError as e:
        return "删除失败: %s" % e
    return None
