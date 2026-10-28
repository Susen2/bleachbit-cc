# TestWinUninstall.py -- enumeration logic tests with a fake registry.
import os
import sys
import unittest
from unittest import mock
import winreg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleachbit import WinUninstall  # noqa: E402
from tests.TestWinStartup import FakeWinreg, _make_module  # noqa: E402

UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


class UninstallEnumTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWinreg()
        self.hkcu = WinUninstall.winreg.HKEY_CURRENT_USER
        self.hklm = WinUninstall.winreg.HKEY_LOCAL_MACHINE
        self.fake.ensure(self.hkcu, UNINSTALL)  # parent key must exist
        self.fake.ensure(self.hkcu, UNINSTALL + "\\AppA")
        self.fake.store[(self.hkcu, UNINSTALL + "\\AppA", 0)] = {
            "DisplayName": ("App A", winreg.REG_SZ),
            "DisplayVersion": ("1.2.3", winreg.REG_SZ),
            "Publisher": ("Vendor", winreg.REG_SZ),
            "EstimatedSize": (10240, winreg.REG_DWORD),
            "UninstallString": ("MsiExec.exe /X{AAA}", winreg.REG_SZ),
            "QuietUninstallString": ("MsiExec.exe /X{AAA} /qn",
                                     winreg.REG_SZ),
        }
        # hidden component: must be skipped
        self.fake.ensure(self.hkcu, UNINSTALL + "\\Hidden")
        self.fake.store[(self.hkcu, UNINSTALL + "\\Hidden", 0)] = {
            "DisplayName": ("Hidden", winreg.REG_SZ),
            "SystemComponent": (1, winreg.REG_DWORD),
        }
        # no DisplayName: must be skipped
        self.fake.ensure(self.hkcu, UNINSTALL + "\\Bare")
        self.fake.store[(self.hkcu, UNINSTALL + "\\Bare", 0)] = {
            "UninstallString": ("whatever.exe", winreg.REG_SZ),
        }
        patcher = mock.patch.object(WinUninstall, "winreg",
                                    _make_module(self.fake))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_list_installed(self):
        programs = WinUninstall.list_installed_programs()
        names = [p.name for p in programs]
        self.assertIn("App A", names)
        self.assertNotIn("Hidden", names)
        program = [p for p in programs if p.name == "App A"][0]
        self.assertEqual(program.version, "1.2.3")
        self.assertEqual(program.estimated_size_kb, 10240)
        self.assertIn("MsiExec.exe", program.uninstall_string)
        self.assertIn("HKCU", program.key_path)

    def test_launch_prefers_quiet_string(self):
        program = WinUninstall.list_installed_programs()[0]
        with mock.patch("bleachbit.WinUninstall.subprocess.Popen") as popen:
            error = WinUninstall.launch_uninstaller(program)
        self.assertIsNone(error)
        called = popen.call_args[0][0]
        self.assertIn("/qn", called)

    def test_launch_without_command_reports_error(self):
        program = WinUninstall.InstalledProgram(
            name="X", version=None, publisher=None,
            install_location=None, uninstall_string=None,
            quiet_string=None, key_path="HKCU\\x")
        error = WinUninstall.launch_uninstaller(program)
        self.assertIsNotNone(error)
        self.assertIn("卸载命令", error)


class RealRegistryReadTest(unittest.TestCase):
    def test_list_real_programs(self):
        programs = WinUninstall.list_installed_programs()
        self.assertIsInstance(programs, list)
        for p in programs:
            self.assertTrue(p.name)
            self.assertTrue(p.key_path)


if __name__ == "__main__":
    unittest.main()
