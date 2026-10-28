# TestWinStartup.py -- logic tests with a fake registry. No real writes.
import os
import sys
import unittest
from unittest import mock
import winreg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleachbit import WinStartup  # noqa: E402


class FakeWinregError(OSError):
    pass


class FakeKey:
    def __init__(self, store, hive, subkey, view):
        self.store = store  # {name: (value, type)}
        self.hive = hive
        self.subkey = subkey
        self.view = view

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    """Minimal in-memory winreg replacement (constants mirror real winreg)."""
    HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
    HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
    KEY_READ = winreg.KEY_READ
    KEY_SET_VALUE = winreg.KEY_SET_VALUE
    KEY_WOW64_64KEY = winreg.KEY_WOW64_64KEY
    KEY_WOW64_32KEY = winreg.KEY_WOW64_32KEY
    REG_SZ = winreg.REG_SZ

    def __init__(self, deny_writes=()):
        self.store = {}  # (hive, subkey, viewmask) -> {name: (val, type)}
        self.deny_writes = set(deny_writes)

    @staticmethod
    def _view(access):
        return access & (winreg.KEY_WOW64_64KEY | winreg.KEY_WOW64_32KEY)

    def OpenKey(self, hive, subkey, reserved=0, access=0):
        entry = self.store.get((hive, subkey, self._view(access)))
        if entry is None:
            raise FakeWinregError(2, "file not found")
        if access & winreg.KEY_SET_VALUE and \
                (hive, subkey, self._view(access)) in self.deny_writes:
            raise PermissionError(5, "access denied")
        return FakeKey(entry, hive, subkey, self._view(access))

    def CreateKey(self, hive, subkey):
        entry = self.store.setdefault((hive, subkey, 0), {})
        return FakeKey(entry, hive, subkey, 0)

    def QueryValueEx(self, key, name):
        if name not in key.store:
            raise FakeWinregError(2, "not found")
        return key.store[name]

    def SetValueEx(self, key, name, reserved, vtype, value):
        key.store[name] = (value, vtype)

    def DeleteValue(self, key, name):
        if name not in key.store:
            raise FakeWinregError(2, "not found")
        del key.store[name]

    def EnumValue(self, key, index):
        items = list(key.store.items())
        if index >= len(items):
            raise FakeWinregError(259, "no more")
        name, (value, vtype) = items[index]
        return name, value, vtype

    def EnumKey(self, key, index):
        prefix = key.subkey + "\\"
        children = sorted({
            s[len(prefix):]
            for (h, s, v) in self.store
            if h == key.hive and v == key.view
            and s.startswith(prefix) and "\\" not in s[len(prefix):]
        })
        if index >= len(children):
            raise FakeWinregError(259, "no more")
        return children[index]

    def ensure(self, hive, subkey, view=0):
        return self.store.setdefault((hive, subkey, view), {})


RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _make_module(fake):
    mod = mock.MagicMock(wraps=winreg)
    for attr in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "KEY_READ",
                 "KEY_SET_VALUE", "KEY_WOW64_64KEY", "KEY_WOW64_32KEY",
                 "REG_SZ"):
        setattr(mod, attr, getattr(fake, attr))
    for fn in ("OpenKey", "CreateKey", "QueryValueEx", "SetValueEx",
               "DeleteValue", "EnumValue", "EnumKey"):
        setattr(mod, fn, getattr(fake, fn))
    return mod


class StartupLogicTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWinreg()
        self.fake.ensure(WinStartup.winreg.HKEY_CURRENT_USER, RUN)
        self.fake.ensure(WinStartup.winreg.HKEY_LOCAL_MACHINE, RUN,
                         winreg.KEY_WOW64_64KEY)
        patcher = mock.patch.object(WinStartup, "winreg",
                                    _make_module(self.fake))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disable_and_enable_roundtrip(self):
        hkcu = WinStartup.winreg.HKEY_CURRENT_USER
        self.fake.store[(hkcu, RUN, 0)]["MyApp"] = ("app.exe -q",
                                                    winreg.REG_SZ)
        entry = WinStartup.StartupEntry(
            kind="registry", location="HKCU\\...\\Run", name="MyApp",
            command="app.exe -q", state="enabled",
            hive=hkcu, subkey=RUN, view=0)
        self.assertIsNone(WinStartup.disable_entry(entry))
        # value removed from Run, stored in backup (CreateKey uses view 0)
        self.assertNotIn("MyApp", self.fake.store[(hkcu, RUN, 0)])
        backup = self.fake.store[(hkcu, WinStartup.BACKUP_KEY, 0)]
        self.assertEqual(backup["HKCU|%s|0\\MyApp" % RUN],
                         ("app.exe -q", winreg.REG_SZ))
        entry.state = "disabled"
        self.assertIsNone(WinStartup.enable_entry(entry))
        self.assertEqual(self.fake.store[(hkcu, RUN, 0)]["MyApp"],
                         ("app.exe -q", winreg.REG_SZ))

    def test_disable_without_admin_reports_error(self):
        hklm = WinStartup.winreg.HKEY_LOCAL_MACHINE
        self.fake.store[(hklm, RUN, winreg.KEY_WOW64_64KEY)]["Svc"] = (
            "svc.exe", winreg.REG_SZ)
        self.fake.deny_writes.add((hklm, RUN, winreg.KEY_WOW64_64KEY))
        entry = WinStartup.StartupEntry(
            kind="registry", location="HKLM(64)\\...\\Run", name="Svc",
            command="svc.exe", state="enabled",
            hive=hklm, subkey=RUN, view=winreg.KEY_WOW64_64KEY)
        error = WinStartup.disable_entry(entry)
        self.assertIsNotNone(error)
        self.assertIn("权限", error)
        # value still present after the failed attempt
        self.assertIn("Svc", self.fake.store[
            (hklm, RUN, winreg.KEY_WOW64_64KEY)])

    def test_delete_entry(self):
        hkcu = WinStartup.winreg.HKEY_CURRENT_USER
        self.fake.store[(hkcu, RUN, 0)]["Gone"] = ("g.exe", winreg.REG_SZ)
        entry = WinStartup.StartupEntry(
            kind="registry", location="HKCU\\...\\Run", name="Gone",
            command="g.exe", state="enabled", hive=hkcu, subkey=RUN,
            view=0)
        self.assertIsNone(WinStartup.delete_entry(entry))
        self.assertNotIn("Gone", self.fake.store[(hkcu, RUN, 0)])

    def test_list_reports_disabled_state(self):
        hkcu = WinStartup.winreg.HKEY_CURRENT_USER
        self.fake.store[(hkcu, RUN, 0)]["Enabled1"] = ("a.exe",
                                                       winreg.REG_SZ)
        self.fake.ensure(hkcu, WinStartup.BACKUP_KEY)
        backup = self.fake.store[(hkcu, WinStartup.BACKUP_KEY, 0)]
        backup["HKCU|%s|0\\Disabled1" % RUN] = ("b.exe", winreg.REG_SZ)
        entries = WinStartup.list_startup_entries()
        by_name = {e.name: e for e in entries if e.kind == "registry"}
        self.assertEqual(by_name["Enabled1"].state, "enabled")
        self.assertEqual(by_name["Disabled1"].state, "disabled")


class RealRegistryReadTest(unittest.TestCase):
    """Read-only tests against the real machine (no writes)."""

    def test_list_startup_entries_returns_list(self):
        entries = WinStartup.list_startup_entries()
        self.assertIsInstance(entries, list)
        for entry in entries:
            self.assertIn(entry.state, ("enabled", "disabled"))
            self.assertTrue(entry.name)

    def test_backup_key_detection(self):
        # no exception with the real registry, returns bool
        result = WinStartup._is_backed_up(
            winreg.HKEY_CURRENT_USER, RUN, 0, "definitely-not-a-value")
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
