# TestGuiWindowCC.py -- unit tests for the CC-style quick preset logic.
# GTK-free: QuickPreset.py contains no view code.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleachbit.QuickPreset import (  # noqa: E402
    QUICK_EXCLUDE_OPTIONS,
    QUICK_EXCLUDE_CLEANERS,
    build_quick_preset,
    preset_summary_lines,
)


def _load_backends():
    from bleachbit.CleanerML import load_cleaners
    list(load_cleaners())  # generator: iterate to actually load


def test_preset_excludes_dangerous_options():
    _load_backends()
    operations = build_quick_preset()
    assert len(operations) > 0, "quick preset must not be empty"
    for cleaner_id, option_ids in operations.items():
        assert cleaner_id not in QUICK_EXCLUDE_CLEANERS
        for option_id in option_ids:
            assert option_id not in QUICK_EXCLUDE_OPTIONS, \
                "%s.%s must not be in the quick preset" % (cleaner_id,
                                                           option_id)


def test_preset_options_have_no_warnings():
    _load_backends()
    from bleachbit.Cleaner import backends
    operations = build_quick_preset()
    for cleaner_id, option_ids in operations.items():
        for option_id in option_ids:
            assert not backends[cleaner_id].get_warning(option_id), \
                "warning options must not be in quick preset"


def test_summary_lines_reference_real_cleaners():
    _load_backends()
    operations = build_quick_preset()
    lines = preset_summary_lines(operations)
    assert len(lines) == len(operations)
    for line in lines:
        assert "：" in line
