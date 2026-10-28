# TestWinRegistry.py -- backup format + fix logic with a fake registry.
import os
import sys
import unittest
from unittest import mock
import winreg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleachbit import WinRegistry  # noqa: E402
from tests.TestWinStartup import FakeWinreg, _make_module  # noqa: E402


class RegistryDisabledByDefaultTest(unittest.TestCase):
    def test_scan_returns_empty_when_disabled(self):
        # fresh test config: registry_cleaner_enabled is unset -> off
        from bleachbit.Options import options
        options.set('registry_cleaner_enabled', False)
        self.assertEqual(WinRegistry.scan_registry(), [])


class FixLogicTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWinreg()
        self.hkcu = WinRegistry.winreg.HKEY_CURRENT_USER
        patcher = mock.patch.object(WinRegistry, "winreg",
                                    _make_module(self.fake))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fix_value_deletion(self):
        key = self.fake.ensure(self.hkcu, r"Software\MuiTest")
        key["Stale.Ref"] = ("x", winreg.REG_SZ)
        issue = WinRegistry.RegistryIssue(
            "MUI 缓存", self.hkcu, r"Software\MuiTest", 0, "Stale.Ref",
            "detail")
        self.assertIsNone(WinRegistry.fix_issue(issue))
        self.assertNotIn("Stale.Ref", key)

    def test_fix_key_deletion(self):
        self.fake.ensure(self.hkcu, r"Software\AppPathsTest\tool.exe")
        parent = self.fake.ensure(self.hkcu, r"Software\AppPathsTest")
        issue = WinRegistry.RegistryIssue(
            "应用路径", self.hkcu, r"Software\AppPathsTest\tool.exe", 0,
            "", "detail", kind="key")
        self.assertIsNone(WinRegistry.fix_issue(issue))
        self.assertNotIn(r"tool.exe", parent)

    def test_permission_error_reported(self):
        run_key = self.fake.ensure(self.hkcu, r"Software\MuiTest")
        run_key["Locked"] = ("x", winreg.REG_SZ)
        self.fake.deny_writes.add(
            (self.hkcu, r"Software\MuiTest", 0))
        issue = WinRegistry.RegistryIssue(
            "MUI 缓存", self.hkcu, r"Software\MuiTest", 0, "Locked",
            "detail")
        error = WinRegistry.fix_issue(issue)
        self.assertIsNotNone(error)
        self.assertIn("权限", error)


class BackupFormatTest(unittest.TestCase):
    def test_backup_contains_value_and_header(self):
        fake = FakeWinreg()
        hkcu = WinRegistry.winreg.HKEY_CURRENT_USER
        key = fake.ensure(hkcu, r"Software\MuiTest")
        key["Stale.Ref"] = ("hello", winreg.REG_SZ)
        patcher = mock.patch.object(WinRegistry, "winreg",
                                    _make_module(fake))
        patcher.start()
        self.addCleanup(patcher.stop)

        import tempfile
        issue = WinRegistry.RegistryIssue(
            "MUI 缓存", hkcu, r"Software\MuiTest", 0, "Stale.Ref",
            "detail")
        backup_path = os.path.join(tempfile.mkdtemp(), "backup.reg")
        WinRegistry.write_reg_backup([issue], backup_path)
        with open(backup_path, encoding="utf-16") as f:
            content = f.read()
        self.assertIn("Windows Registry Editor Version 5.00", content)
        self.assertIn("[HKEY_CURRENT_USER\\Software\\MuiTest]", content)
        self.assertIn('"Stale.Ref"=hex(00000001):', content)
        # 'hello' in UTF-16LE hex
        self.assertIn("68,00,65,00,6c,00,6c,00,6f,00,00,00", content)


if __name__ == "__main__":
    unittest.main()
