# SPDX-License-Identifier: GPL-3.0-or-later
# Small shared helpers for the tools pages.

from bleachbit.GtkShim import Gtk


def make_placeholder(text):
    """A centered placeholder page for tools not yet implemented."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    label = Gtk.Label.new(text)
    label.set_valign(Gtk.Align.CENTER)
    label.get_style_context().add_class('dim-label')
    box.pack_start(label, True, True, 0)
    return box
