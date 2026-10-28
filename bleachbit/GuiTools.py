# SPDX-License-Identifier: GPL-3.0-or-later
# Tools page for the CC-style shell: startup manager and uninstaller.

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


def build_tools_notebook(window):
    """Create the tools notebook with all tabs (placeholders for M3/M4)."""
    from bleachbit.GuiToolsExtra import make_placeholder
    notebook = Gtk.Notebook()
    notebook.append_page(StartupTool(window).box, Gtk.Label.new(_("启动项")))
    notebook.append_page(UninstallTool(window).box,
                         Gtk.Label.new(_("卸载器")))
    notebook.append_page(make_placeholder(_("重复文件查找将在后续里程碑提供。")),
                         Gtk.Label.new(_("重复文件")))
    notebook.append_page(make_placeholder(_("磁盘分析将在后续里程碑提供。")),
                         Gtk.Label.new(_("磁盘分析")))
    notebook.append_page(make_placeholder(
        _("注册表清理将在后续里程碑提供（默认关闭）。")),
        Gtk.Label.new(_("注册表清理")))
    return notebook
