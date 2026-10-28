# SPDX-License-Identifier: GPL-3.0-or-later
# Tools page for the CC-style shell: startup manager, uninstaller,
# duplicate finder and disk analyzer.

import os

from bleachbit.GtkShim import Gtk, GLib
from bleachbit.Language import get_text as _
from bleachbit import FileUtilities


def _confirm(parent, title, text):
    """Yes/No confirmation dialog. Returns True when confirmed."""
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True,
                               message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.YES_NO, text=title)
    dialog.format_secondary_text(text)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


def _error(parent, text):
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True,
                               message_type=Gtk.MessageType.ERROR,
                               buttons=Gtk.ButtonsType.OK, text=text)
    dialog.run()
    dialog.destroy()


class StartupTool:
    """Startup manager tab."""

    def __init__(self, window):
        self.window = window
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)

        bar = Gtk.Box(homogeneous=False, spacing=6)
        refresh = Gtk.Button.new_with_label(_("刷新"))
        refresh.connect("clicked", lambda _w: self.refresh())
        disable = Gtk.Button.new_with_label(_("禁用"))
        disable.connect("clicked", self._on_disable)
        enable = Gtk.Button.new_with_label(_("启用"))
        enable.connect("clicked", self._on_enable)
        delete = Gtk.Button.new_with_label(_("删除"))
        delete.connect("clicked", self._on_delete)
        for b in (refresh, disable, enable, delete):
            bar.pack_start(b, False, False, 0)
        self.box.pack_start(bar, False, False, 0)

        # columns: state, name, command, location
        self.store = Gtk.ListStore(str, str, str, str, object)
        view = Gtk.TreeView(model=self.store)
        for i, title in enumerate((_("状态"), _("名称"), _("命令"),
                                   _("位置"))):
            cell = Gtk.CellRendererText()
            cell.set_property("ellipsize", 3 if i == 2 else 0)
            column = Gtk.TreeViewColumn(title, cell, text=i)
            column.set_resizable(True)
            if i == 2:
                column.set_expand(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_property('expand', True)
        scroll.add(view)
        self.box.add(scroll)
        GLib.idle_add(self.refresh)

    def _selected(self):
        model, tree_iter = self._view.get_selection().get_selected()
        if tree_iter is None:
            return None
        return model[tree_iter][4]

    def refresh(self, *_args):
        from bleachbit import WinStartup
        self.store.clear()
        try:
            entries = WinStartup.list_startup_entries()
        except Exception as e:
            _error(self.window, _("枚举启动项失败: %s") % e)
            return False
        for entry in entries:
            state_text = _("已禁用") if entry.state == "disabled" \
                else _("已启用")
            self.store.append([state_text, entry.name, entry.command,
                               entry.location, entry])
        return False

    def _act(self, fn, success_hint):
        entry = self._selected()
        if entry is None:
            return
        error = fn(entry)
        if error:
            _error(self.window, error)
        else:
            self.refresh()
            self.window.append_text(success_hint + "\n")

    def _on_disable(self, _widget):
        entry = self._selected()
        if entry is None:
            return
        if not _confirm(self.window, _("禁用启动项“%s”？") % entry.name,
                        _("可以通过“启用”随时恢复。")):
            return
        self._act(lambda e: self._module().disable_entry(e),
                  _("已禁用: %s") % entry.name)

    def _on_enable(self, _widget):
        entry = self._selected()
        if entry is None:
            return
        self._act(lambda e: self._module().enable_entry(e),
                  _("已启用: %s") % entry.name)

    def _on_delete(self, _widget):
        entry = self._selected()
        if entry is None:
            return
        if not _confirm(self.window, _("删除启动项“%s”？") % entry.name,
                        _("这是永久删除，不能通过“启用”恢复。")):
            return
        self._act(lambda e: self._module().delete_entry(e),
                  _("已删除: %s") % entry.name)

    @staticmethod
    def _module():
        from bleachbit import WinStartup
        return WinStartup

    @property
    def _view(self):
        # the tree view is the child of the scrolled window
        return self.box.get_children()[1].get_child()


class UninstallTool:
    """Installed programs / uninstaller tab."""

    def __init__(self, window):
        self.window = window
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)

        bar = Gtk.Box(homogeneous=False, spacing=6)
        refresh = Gtk.Button.new_with_label(_("刷新"))
        refresh.connect("clicked", lambda _w: self.refresh())
        uninstall = Gtk.Button.new_with_label(_("卸载"))
        uninstall.connect("clicked", self._on_uninstall)
        for b in (refresh, uninstall):
            bar.pack_start(b, False, False, 0)
        self.box.pack_start(bar, False, False, 0)

        # columns: name, version, publisher, size, has-uninstaller
        self.store = Gtk.ListStore(str, str, str, str, str, object)
        view = Gtk.TreeView(model=self.store)
        for i, title in enumerate((_("程序"), _("版本"), _("发布者"),
                                   _("大小"), _("卸载命令"))):
            cell = Gtk.CellRendererText()
            cell.set_property("ellipsize", 0)
            column = Gtk.TreeViewColumn(title, cell, text=i)
            column.set_resizable(True)
            if i == 0:
                column.set_expand(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_property('expand', True)
        scroll.add(view)
        self.box.add(scroll)
        GLib.idle_add(self.refresh)

    def _selected(self):
        model, tree_iter = self._view.get_selection().get_selected()
        if tree_iter is None:
            return None
        return model[tree_iter][5]

    def refresh(self, *_args):
        from bleachbit import WinUninstall
        self.store.clear()
        try:
            programs = WinUninstall.list_installed_programs()
        except Exception as e:
            _error(self.window, _("枚举已安装程序失败: %s") % e)
            return False
        for program in programs:
            size = "-"
            if program.estimated_size_kb:
                size = FileUtilities.bytes_to_human(
                    program.estimated_size_kb * 1024)
            has_uninstall = _("有") if (program.uninstall_string
                                       or program.quiet_string) else _("无")
            self.store.append([program.name, program.version or "",
                               program.publisher or "", size,
                               has_uninstall, program])
        return False

    def _on_uninstall(self, _widget):
        program = self._selected()
        if program is None:
            return
        if not program.uninstall_string and not program.quiet_string:
            _error(self.window, _("该程序没有记录卸载命令"))
            return
        mode = _("静默卸载") if program.quiet_string else _("运行卸载程序")
        if not _confirm(self.window,
                        _("卸载“%s”？") % program.name,
                        _("将以“%s”方式执行厂商的卸载命令。\n"
                          "完成后请点击“刷新”更新列表。") % mode):
            return
        from bleachbit import WinUninstall
        error = WinUninstall.launch_uninstaller(program)
        if error:
            _error(self.window, error)
        else:
            self.window.append_text(
                _("已启动 %s 的卸载程序。") % program.name + "\n")

    @property
    def _view(self):
        return self.box.get_children()[1].get_child()


class DuplicateTool:
    """Duplicate file finder tab."""

    def __init__(self, window):
        self.window = window
        self._stop_flag = False
        self._scanning = False
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)

        path_row = Gtk.Box(homogeneous=False, spacing=6)
        path_row.pack_start(Gtk.Label.new(_("目录：")), False, False, 0)
        self.path_entry = Gtk.Entry()
        self.path_entry.set_text(os.path.expanduser("~"))
        self.path_entry.set_hexpand(True)
        path_row.pack_start(self.path_entry, True, True, 0)
        browse = Gtk.Button.new_with_label(_("浏览…"))
        browse.connect("clicked", self._on_browse)
        path_row.pack_start(browse, False, False, 0)
        self.box.add(path_row)

        bar = Gtk.Box(homogeneous=False, spacing=6)
        self.scan_button = Gtk.Button.new_with_label(_("开始扫描"))
        self.scan_button.connect("clicked", self._on_scan)
        stop = Gtk.Button.new_with_label(_("停止"))
        stop.connect("clicked", self._on_stop)
        self.delete_button = Gtk.Button.new_with_label(_("删除所选文件"))
        self.delete_button.set_sensitive(False)
        self.delete_button.connect("clicked", self._on_delete_selected)
        for b in (self.scan_button, stop, self.delete_button):
            bar.pack_start(b, False, False, 0)
        self.summary_label = Gtk.Label.new("")
        self.summary_label.set_halign(Gtk.Align.START)
        bar.pack_start(self.summary_label, False, False, 0)
        self.box.add(bar)

        # columns: size, path, full path (hidden)
        self.store = Gtk.ListStore(str, str, str)
        view = Gtk.TreeView(model=self.store)
        view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        for i, title in enumerate((_("大小"), _("重复文件"))):
            cell = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, cell, text=i)
            column.set_resizable(True)
            if i == 1:
                column.set_expand(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_property('expand', True)
        scroll.add(view)
        self.box.add(scroll)

    def _on_browse(self, _widget):
        from bleachbit import GuiBasic
        folder = GuiBasic.browse_folder(self.window, _("选择要扫描的目录"))
        if folder:
            self.path_entry.set_text(folder)

    def _on_stop(self, _widget):
        self._stop_flag = True

    def _on_scan(self, _widget):
        if self._scanning:
            return
        root = self.path_entry.get_text().strip()
        if not os.path.isdir(root):
            _error(self.window, _("目录无效: %s") % root)
            return
        self._scanning = True
        self._stop_flag = False
        self.scan_button.set_sensitive(False)
        self.delete_button.set_sensitive(False)
        self.store.clear()
        self.summary_label.set_text(_("正在扫描……"))
        import threading
        thread = threading.Thread(target=self._scan_worker, args=(root,),
                                  daemon=True)
        thread.start()

    def _scan_worker(self, root):
        from bleachbit import DuplicateFinder

        def progress(done, groups):
            GLib.idle_add(self.summary_label.set_text,
                          _("已检查 %d 个文件，发现 %d 组重复") % (done, groups))

        try:
            groups = DuplicateFinder.scan_duplicates(
                [root], progress_cb=progress,
                should_continue=lambda: not self._stop_flag)
        except Exception as e:
            GLib.idle_add(self._scan_done, None, str(e))
            return
        GLib.idle_add(self._scan_done, groups, None)

    def _scan_done(self, groups, error):
        self._scanning = False
        self.scan_button.set_sensitive(True)
        if error:
            self.summary_label.set_text(_("扫描失败: %s") % error)
            return False
        if groups is None:  # stopped
            self.summary_label.set_text(_("已停止。"))
            return False
        from bleachbit import FileUtilities
        total_waste = sum(g["size"] * (len(g["paths"]) - 1)
                          for g in groups)
        count = sum(len(g["paths"]) for g in groups)
        for group in groups:
            for path in group["paths"]:
                self.store.append([FileUtilities.bytes_to_human(
                    group["size"]), path, path])
        self.summary_label.set_text(
            _("发现 %d 组重复（%d 个文件），可释放约 %s") %
            (len(groups), count,
             FileUtilities.bytes_to_human(total_waste)))
        self.delete_button.set_sensitive(count > 0)
        return False

    def _on_delete_selected(self, _widget):
        model, paths = self._view.get_selection().get_selected_rows()
        files = [model[p][2] for p in paths]
        if not files:
            return
        if not _confirm(self.window,
                        _("永久删除选中的 %d 个文件？") % len(files),
                        _("此操作不可恢复（不进回收站）。")):
            return
        failures = 0
        for path in files:
            try:
                os.remove(path)
            except OSError:
                failures += 1
        if failures:
            _error(self.window, _("%d 个文件删除失败。") % failures)
        self.window.append_text(
            _("已删除 %d 个重复文件。") % (len(files) - failures) + "\n")
        self._on_scan(None)

    @property
    def _view(self):
        return self.box.get_children()[2].get_child()


class DiskTool:
    """Disk usage analyzer tab."""

    def __init__(self, window):
        self.window = window
        self._stop_flag = False
        self._scanning = False
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)

        path_row = Gtk.Box(homogeneous=False, spacing=6)
        path_row.pack_start(Gtk.Label.new(_("目录：")), False, False, 0)
        self.path_entry = Gtk.Entry()
        self.path_entry.set_text(os.path.expanduser("~"))
        self.path_entry.set_hexpand(True)
        path_row.pack_start(self.path_entry, True, True, 0)
        browse = Gtk.Button.new_with_label(_("浏览…"))
        browse.connect("clicked", self._on_browse)
        path_row.pack_start(browse, False, False, 0)
        self.box.add(path_row)

        bar = Gtk.Box(homogeneous=False, spacing=6)
        self.scan_button = Gtk.Button.new_with_label(_("开始分析"))
        self.scan_button.connect("clicked", self._on_scan)
        stop = Gtk.Button.new_with_label(_("停止"))
        stop.connect("clicked", lambda _w: setattr(self, "_stop_flag", True))
        for b in (self.scan_button, stop):
            bar.pack_start(b, False, False, 0)
        self.summary_label = Gtk.Label.new("")
        self.summary_label.set_halign(Gtk.Align.START)
        bar.pack_start(self.summary_label, False, False, 0)
        self.box.add(bar)

        self.store = Gtk.ListStore(str, str)
        view = Gtk.TreeView(model=self.store)
        for i, title in enumerate((_("目录"), _("占用空间"))):
            cell = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, cell, text=i)
            column.set_resizable(True)
            if i == 0:
                column.set_expand(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_property('expand', True)
        scroll.add(view)
        self.box.add(scroll)

    def _on_browse(self, _widget):
        from bleachbit import GuiBasic
        folder = GuiBasic.browse_folder(self.window, _("选择要分析的目录"))
        if folder:
            self.path_entry.set_text(folder)

    def _on_scan(self, _widget):
        if self._scanning:
            return
        root = self.path_entry.get_text().strip()
        if not os.path.isdir(root):
            _error(self.window, _("目录无效: %s") % root)
            return
        self._scanning = True
        self._stop_flag = False
        self.scan_button.set_sensitive(False)
        self.store.clear()
        self.summary_label.set_text(_("正在分析……"))
        import threading
        thread = threading.Thread(target=self._scan_worker, args=(root,),
                                  daemon=True)
        thread.start()

    def _scan_worker(self, root):
        from bleachbit import DiskAnalyzer
        try:
            results = DiskAnalyzer.scan_dir_sizes(
                root, should_continue=lambda: not self._stop_flag)
        except Exception as e:
            GLib.idle_add(self._scan_done, None, str(e))
            return
        GLib.idle_add(self._scan_done, results, None)

    def _scan_done(self, results, error):
        self._scanning = False
        self.scan_button.set_sensitive(True)
        if error:
            self.summary_label.set_text(_("分析失败: %s") % error)
            return False
        if results is None:
            self.summary_label.set_text(_("已停止。"))
            return False
        from bleachbit import FileUtilities
        for path, size in results[:100]:
            self.store.append([path, FileUtilities.bytes_to_human(size)])
        self.summary_label.set_text(
            _("共 %d 个目录，按占用空间排序（显示前 100）。") % len(results))
        return False

    @property
    def _view(self):
        return self.box.get_children()[2].get_child()


class RegistryTool:
    """Opt-in registry cleaner tab (backup before any fix)."""

    def __init__(self, window):
        self.window = window
        self._issues = []
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_margin_top(8)
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)

        notice = Gtk.Label.new(_(
            "高级功能，默认关闭。修复前会自动导出 .reg 备份到"
            "“文档\\BleachBitCC-Backups”，可用 reg import 还原。"))
        notice.set_halign(Gtk.Align.START)
        notice.set_line_wrap(True)
        self.box.add(notice)

        enable_row = Gtk.Box(homogeneous=False, spacing=8)
        enable_label = Gtk.Label.new(_("启用注册表清理"))
        enable_label.set_halign(Gtk.Align.START)
        self.enable_switch = Gtk.Switch()
        self.enable_switch.set_active(self._enabled())
        self.enable_switch.connect("notify::active", self._on_enable)
        enable_row.pack_start(enable_label, False, False, 0)
        enable_row.pack_end(self.enable_switch, False, False, 0)
        self.box.add(enable_row)

        bar = Gtk.Box(homogeneous=False, spacing=6)
        self.scan_button = Gtk.Button.new_with_label(_("开始扫描"))
        self.scan_button.set_sensitive(self._enabled())
        self.scan_button.connect("clicked", self._on_scan)
        self.fix_button = Gtk.Button.new_with_label(_("备份并修复所选"))
        self.fix_button.set_sensitive(False)
        self.fix_button.connect("clicked", self._on_fix)
        for b in (self.scan_button, self.fix_button):
            bar.pack_start(b, False, False, 0)
        self.summary_label = Gtk.Label.new("")
        self.summary_label.set_halign(Gtk.Align.START)
        bar.pack_start(self.summary_label, False, False, 0)
        self.box.add(bar)

        # columns: selected, category, path, detail
        self.store = Gtk.ListStore(bool, str, str, str, object)
        view = Gtk.TreeView(model=self.store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggle)
        view.append_column(Gtk.TreeViewColumn(_("选中"), toggle,
                                              active=0))
        for i, title in enumerate((_("类别"), _("注册表路径"), _("问题"))):
            cell = Gtk.CellRendererText()
            cell.set_property("ellipsize", 0)
            column = Gtk.TreeViewColumn(title, cell, text=i)
            column.set_resizable(True)
            if i == 2:
                column.set_expand(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_property('expand', True)
        scroll.add(view)
        self.box.add(scroll)

    @staticmethod
    def _enabled():
        from bleachbit.WinRegistry import is_registry_cleaner_enabled
        return is_registry_cleaner_enabled()

    def _on_enable(self, switch, _param):
        from bleachbit.Options import options
        options.set('registry_cleaner_enabled', switch.get_active())
        self.scan_button.set_sensitive(switch.get_active())
        if not switch.get_active():
            self.store.clear()
            self._issues = []
            self.fix_button.set_sensitive(False)
            self.summary_label.set_text("")

    def _on_toggle(self, _renderer, path):
        self.store[path][0] = not self.store[path][0]

    def _on_scan(self, _widget):
        import threading
        self.scan_button.set_sensitive(False)
        self.store.clear()
        self._issues = []
        self.fix_button.set_sensitive(False)
        self.summary_label.set_text(_("正在扫描……"))
        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()

    def _scan_worker(self):
        from bleachbit import WinRegistry
        try:
            issues = WinRegistry.scan_registry()
        except Exception as e:
            GLib.idle_add(self._scan_done, None, str(e))
            return
        GLib.idle_add(self._scan_done, issues, None)

    def _scan_done(self, issues, error):
        self.scan_button.set_sensitive(True)
        if error:
            self.summary_label.set_text(_("扫描失败: %s") % error)
            return False
        self._issues = issues
        for issue in issues:
            self.store.append([True, issue.category, issue.full_path,
                               issue.detail, issue])
        self.summary_label.set_text(
            _("发现 %d 个问题（HKLM 项需要管理员权限）。") % len(issues))
        self.fix_button.set_sensitive(bool(issues))
        return False

    def _on_fix(self, _widget):
        selected = [row[4] for row in self.store if row[0]]
        if not selected:
            return
        backup_dir = os.path.join(
            os.path.expanduser("~"), "Documents",
            "BleachBitCC-Backups")
        os.makedirs(backup_dir, exist_ok=True)
        import time
        backup_path = os.path.join(
            backup_dir, "registry-backup-%s.reg" %
            time.strftime("%Y%m%d-%H%M%S"))
        try:
            from bleachbit.WinRegistry import write_reg_backup
            write_reg_backup(selected, backup_path)
        except Exception as e:
            _error(self.window, _("导出备份失败，已取消修复: %s") % e)
            return
        if not _confirm(
                self.window,
                _("删除选中的 %d 项？") % len(selected),
                _("已导出备份：\n%s\n\n确认后执行删除。") % backup_path):
            return
        failures = []
        from bleachbit.WinRegistry import fix_issue
        for issue in selected:
            error = fix_issue(issue)
            if error:
                failures.append("%s: %s" % (issue.full_path, error))
        if failures:
            _error(self.window, _("部分条目修复失败：\n") + "\n".join(
                failures[:10]))
        self.window.append_text(
            _("注册表清理完成：修复 %d 项，失败 %d 项，备份 %s") %
            (len(selected) - len(failures), len(failures),
             backup_path) + "\n")
        self._on_scan(None)

    @property
    def _view(self):
        return self.box.get_children()[3].get_child()


def build_tools_notebook(window):
    """Create the tools notebook with all tabs."""
    notebook = Gtk.Notebook()
    notebook.append_page(StartupTool(window).box, Gtk.Label.new(_("启动项")))
    notebook.append_page(UninstallTool(window).box,
                         Gtk.Label.new(_("卸载器")))
    notebook.append_page(DuplicateTool(window).box,
                         Gtk.Label.new(_("重复文件")))
    notebook.append_page(DiskTool(window).box,
                         Gtk.Label.new(_("磁盘分析")))
    notebook.append_page(RegistryTool(window).box,
                         Gtk.Label.new(_("注册表清理")))
    return notebook
