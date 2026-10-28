# SPDX-License-Identifier: GPL-3.0-or-later
# CC-style beginner-friendly shell for BleachBit (secondary development).
# Parallel to the original GUI: select via options key `cc_layout`
# (default: on) or environment variable BLEACHBIT_CLASSIC_GUI=1.
#
# Layout: left icon sidebar -> four pages:
#   quick   - one-click clean with a safe recommended preset
#   custom  - the original cleaner tree + log (migrated unchanged)
#   tools   - startup manager / uninstaller / duplicates / disk analyzer /
#             registry cleaner (filled by later milestones)
#   options - shortcuts into the stock preferences dialog

import os

from bleachbit.GtkShim import Gtk, GLib
from bleachbit.GuiWindow import GUI
from bleachbit.Language import get_text as _
from bleachbit.Options import options
from bleachbit import FileUtilities
from bleachbit.QuickPreset import (
    QUICK_EXCLUDE_CLEANERS,
    QUICK_EXCLUDE_OPTIONS,
    build_quick_preset,
    preset_summary_lines,
)


class CCGUI(GUI):
    """BleachBit main window with a CCleaner-style page shell."""

    def populate_window(self):
        """Create the main application window (CC-style shell)"""
        screen = self.get_screen()
        display = screen.get_display()
        monitor = display.get_primary_monitor()
        if monitor is None:
            if display.get_n_monitors() > 0:
                monitor = display.get_monitor(0)
        if monitor is None:
            self.set_default_size(900, 640)
        else:
            geometry = monitor.get_geometry()
            self.set_default_size(min(geometry.width, 980),
                                  min(geometry.height, 660))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("configure-event", self.on_configure_event)
        self.connect("window-state-event", self.on_window_state_event)
        self.connect("delete-event", self.on_delete_event)
        self.connect("show", self.on_show)

        from bleachbit.GuiWindow import appicon_path
        if appicon_path and os.path.exists(appicon_path):
            self.set_icon_from_file(appicon_path)

        self.headerbar = self.create_headerbar()
        self.set_titlebar(self.headerbar)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, homogeneous=False)
        self.add(vbox)
        self._build_infobar(vbox)

        hbox = Gtk.Box(homogeneous=False)
        vbox.add(hbox)

        # ---- left: page navigation -----------------------------------
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(self.stack)
        sidebar.set_size_request(148, -1)
        hbox.pack_start(sidebar, False, False, 0)
        hbox.add(self.stack)

        # ---- page 1: one-click clean ---------------------------------
        self.stack.add_titled(self._build_quick_page(), 'quick', _("一键清理"))

        # ---- page 2: custom clean (original layout, migrated) --------
        self.stack.add_titled(self._build_custom_page(), 'custom',
                              _("自定义清理"))

        # ---- page 3: tools --------------------------------------------
        self.stack.add_titled(self._build_tools_page(), 'tools', _("工具"))

        # ---- page 4: options ------------------------------------------
        self.stack.add_titled(self._build_options_page(), 'options', _("选项"))

        # ---- bookkeeping identical to the original window -------------
        self.status_bar = Gtk.Statusbar()
        vbox.add(self.status_bar)
        self.setup_drag_n_drop()
        self._quick_total = 0
        self._quick_active = False
        self.show_all()
        self.progressbar.hide()
        self.infobar.hide()

    # ------------------------------------------------------------------
    # page builders
    # ------------------------------------------------------------------
    def _build_custom_page(self):
        """The original two-pane layout (cleaner tree + log), wrapped."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.set_margin_top(8)
        page.set_margin_bottom(8)
        page.set_margin_start(8)
        page.set_margin_end(8)
        page.set_border_width(6)

        hbox = Gtk.Box(homogeneous=False)
        operations = self.create_operations_box()
        operations.set_size_request(300, -1)
        hbox.pack_start(operations, False, True, 0)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.progressbar = Gtk.ProgressBar()
        right_box.pack_start(self.progressbar, False, True, 0)

        self.textbuffer = Gtk.TextBuffer()
        swindow = Gtk.ScrolledWindow()
        swindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        swindow.set_property('expand', True)
        self.textview = Gtk.TextView.new_with_buffer(self.textbuffer)
        self.textview.set_editable(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        swindow.add(self.textview)
        right_box.add(swindow)
        hbox.add(right_box)
        page.add(hbox)

        # markup tags used by append_text()
        tt = self.textbuffer.get_tag_table()
        style_operation = Gtk.TextTag.new('operation')
        style_operation.set_property('size-points', 14)
        style_operation.set_property('weight', 700)
        style_operation.set_property('pixels-above-lines', 10)
        style_operation.set_property('justification', Gtk.Justification.CENTER)
        tt.add(style_operation)
        style_description = Gtk.TextTag.new('description')
        style_description.set_property(
            'justification', Gtk.Justification.CENTER)
        tt.add(style_description)
        style_option_label = Gtk.TextTag.new('option_label')
        style_option_label.set_property('weight', 700)
        style_option_label.set_property('left-margin', 20)
        tt.add(style_option_label)
        style_error = Gtk.TextTag.new('error')
        tt.add(style_error)
        self.textview.connect('style-updated', self._update_error_tag_color)
        self._update_error_tag_color()
        return page

    def _build_quick_page(self):
        """One-click clean page for beginners."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for attr in ('margin_top', 'margin_bottom'):
            page.set_property(attr, 18)
        page.set_margin_start(24)
        page.set_margin_end(24)

        title = Gtk.Label.new(_("一键清理"))
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class('title-1')
        page.pack_start(title, False, False, 0)

        subtitle = Gtk.Label.new(_(
            "按推荐配置检查并清理无用的缓存和痕迹。不会删除密码、Cookie 和个人文件。"))
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_line_wrap(True)
        page.pack_start(subtitle, False, False, 0)

        # preset content list
        frame = Gtk.Frame()
        frame.set_label(_("本次将清理以下项目（可在“自定义清理”中调整）"))
        self.quick_preset_label = Gtk.Label.new(_("正在加载清理规则……"))
        self.quick_preset_label.set_halign(Gtk.Align.START)
        self.quick_preset_label.set_valign(Gtk.Align.START)
        self.quick_preset_label.set_line_wrap(True)
        self.quick_preset_label.set_xalign(0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(160)
        scroll.add(self.quick_preset_label)
        frame.add(scroll)
        page.pack_start(frame, True, True, 0)

        # big status + buttons
        self.quick_status = Gtk.Label.new(_("点击“开始检查”查看可释放的空间。"))
        self.quick_status.set_halign(Gtk.Align.CENTER)
        page.pack_start(self.quick_status, False, False, 0)

        self.quick_total_label = Gtk.Label.new("")
        self.quick_total_label.set_halign(Gtk.Align.CENTER)
        self.quick_total_label.get_style_context().add_class('title-2')
        page.pack_start(self.quick_total_label, False, False, 0)

        button_box = Gtk.Box(homogeneous=False, spacing=12)
        button_box.set_halign(Gtk.Align.CENTER)
        self.quick_scan_button = Gtk.Button.new_with_mnemonic(_("开始检查"))
        self.quick_scan_button.set_size_request(160, 44)
        self.quick_scan_button.connect(
            "clicked", self.on_quick_scan_clicked)
        button_box.pack_start(self.quick_scan_button, False, False, 0)

        self.quick_clean_button = Gtk.Button.new_with_mnemonic(_("立即清理"))
        self.quick_clean_button.set_size_request(160, 44)
        self.quick_clean_button.get_style_context().add_class(
            'suggested-action')
        self.quick_clean_button.set_sensitive(False)
        self.quick_clean_button.connect(
            "clicked", self.on_quick_clean_clicked)
        button_box.pack_start(self.quick_clean_button, False, False, 0)
        page.pack_start(button_box, False, False, 0)

        hint = Gtk.Label.new(_("提示：清理浏览器缓存前请关闭浏览器；"
                               "检查结果仅预览，不会删除任何文件。"))
        hint.set_halign(Gtk.Align.CENTER)
        hint.get_style_context().add_class('dim-label')
        page.pack_start(hint, False, False, 0)
        return page

    def _build_tools_page(self):
        """Tools page: startup manager, uninstaller (M2), more in M3/M4."""
        from bleachbit.GuiTools import build_tools_notebook
        return build_tools_notebook(self)

    def _build_options_page(self):
        """Options shortcuts page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(18)
        page.set_margin_start(24)
        page.set_margin_end(24)

        title = Gtk.Label.new(_("选项"))
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class('title-1')
        page.pack_start(title, False, False, 0)

        # classic layout escape hatch (constraint: parallel GUI + toggle)
        classic_row = Gtk.Box(homogeneous=False, spacing=8)
        classic_label = Gtk.Label.new(_("使用经典界面（重启后生效）"))
        classic_label.set_halign(Gtk.Align.START)
        classic_switch = Gtk.Switch()
        classic_switch.set_active(options.get('cc_layout') is False)
        classic_switch.connect('notify::active', self._on_classic_switch)
        classic_row.pack_start(classic_label, False, False, 0)
        classic_row.pack_end(classic_switch, False, False, 0)
        page.pack_start(classic_row, False, False, 0)

        full_prefs = Gtk.Button.new_with_label(_("打开完整选项"))
        full_prefs.connect("clicked", lambda _w: self.show_preferences_dialog())
        page.pack_start(full_prefs, False, False, 0)
        return page

    # ------------------------------------------------------------------
    # quick page callbacks
    # ------------------------------------------------------------------
    def _refresh_quick_preset_label(self):
        try:
            operations = build_quick_preset()
        except Exception:
            self.quick_preset_label.set_text(_("清理规则尚未加载完成。"))
            return None
        if not operations:
            self.quick_preset_label.set_text(_("没有可安全清理的项目。"))
            return None
        lines = preset_summary_lines(operations)
        self.quick_preset_label.set_text("\n".join("• " + ln for ln in lines))
        return operations

    def on_quick_scan_clicked(self, _widget):
        """Run a preview with the recommended preset."""
        if not self.run_button_get_sensitive():
            return
        operations = self._refresh_quick_preset_label()
        if not operations:
            return
        self._quick_active = True
        self._quick_total = 0
        self._quick_last_operations = operations
        self.quick_total_label.set_text("")
        self.quick_status.set_text(_("正在检查……"))
        self.quick_clean_button.set_sensitive(False)
        self.preview_or_run_operations(False, operations)

    def on_quick_clean_clicked(self, _widget):
        """Delete what the preview found, with the standard confirmation."""
        if not self.run_button_get_sensitive():
            return
        operations = getattr(self, '_quick_last_operations', None)
        if not operations:
            return
        if self._confirm_delete(True):
            self._quick_active = True
            self._quick_total = 0
            self.quick_total_label.set_text("")
            self.quick_status.set_text(_("正在清理……"))
            self.preview_or_run_operations(True, operations)

    def _on_classic_switch(self, switch, _param):
        options.set('cc_layout', not switch.get_active())
        if switch.get_active():
            self.append_text(_("经典界面已启用，重启 BleachBit 后生效。") + "\n")

    # ------------------------------------------------------------------
    # hooks into the worker machinery
    # ------------------------------------------------------------------
    def update_item_size(self, option, option_id, bytes_removed):
        """Accumulate the quick-page total from per-operation summaries."""
        super().update_item_size(option, option_id, bytes_removed)
        if self._quick_active and option_id == -1 and bytes_removed > 0:
            self._quick_total += bytes_removed

    def update_total_size(self, bytes_removed):
        super().update_total_size(bytes_removed)
        if self._quick_active:
            self._quick_total = max(self._quick_total, bytes_removed)

    def worker_done(self, worker, really_delete):
        super().worker_done(worker, really_delete)
        if not self._quick_active:
            return
        self._quick_active = False
        total = self._quick_total
        if really_delete:
            self.quick_status.set_text(_("清理完成！"))
            self.quick_total_label.set_text(
                _("已释放 %s 空间") % FileUtilities.bytes_to_human(total))
        else:
            self.quick_status.set_text(_("检查完成。确认无误后点击“立即清理”。"))
            self.quick_total_label.set_text(
                _("可释放约 %s 空间") % FileUtilities.bytes_to_human(total))
            self.quick_clean_button.set_sensitive(True)

    def set_sensitive(self, is_sensitive):
        super().set_sensitive(is_sensitive)
        if hasattr(self, 'quick_scan_button'):
            self.quick_scan_button.set_sensitive(is_sensitive)
            if is_sensitive:
                self.quick_clean_button.set_sensitive(
                    getattr(self, '_quick_last_operations', None) is not None
                    and not self._quick_active)
            else:
                self.quick_clean_button.set_sensitive(False)

    def cb_register_cleaners_done(self):
        """Refresh the preset summary once cleaners are registered."""
        super().cb_register_cleaners_done()
        GLib.idle_add(self._refresh_quick_preset_label)
