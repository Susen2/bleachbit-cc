# SPDX-License-Identifier: GPL-3.0-or-later
# Quick-clean preset logic for the CC-style shell. GTK-free so it can be
# unit tested headlessly.

# Options that must never run silently from the one-click page because
# they destroy data a beginner would not expect to lose.
QUICK_EXCLUDE_OPTIONS = {
    'free',              # wiping free space takes hours and has no undo
    'cookies',           # logs the user out of every web site
    'saved_form_info',
    'passwords',
    'autofill',
    'session',
    'vacuum',
    'custom',
    'files',             # generic "files" options are too broad
}
QUICK_EXCLUDE_CLEANERS = {
    'deepscan',          # deep scan can match files the user still wants
    '_gui',              # synthetic cleaner for wipe-empty-space
}


def build_quick_preset():
    """Return {cleaner_id: [option_id, ...]} for the recommended preset.

    Only options without a warning label are included, and the exclusion
    sets above are always honored.
    """
    from bleachbit.Cleaner import backends
    operations = {}
    for cleaner_id, cleaner in backends.items():
        if cleaner_id in QUICK_EXCLUDE_CLEANERS:
            continue
        safe_options = []
        for option_id, _option_name in cleaner.get_options():
            if option_id in QUICK_EXCLUDE_OPTIONS:
                continue
            if cleaner.get_warning(option_id):
                continue
            safe_options.append(option_id)
        if safe_options:
            operations[cleaner_id] = safe_options
    return operations


def preset_summary_lines(operations):
    """Human-readable list of what the preset will clean."""
    from bleachbit.Cleaner import backends
    lines = []
    for cleaner_id, option_ids in operations.items():
        cleaner = backends[cleaner_id]
        option_names = []
        for oid in option_ids:
            for (oid_known, oname) in cleaner.get_options():
                if oid_known == oid:
                    option_names.append(oname)
                    break
            else:
                option_names.append(oid)
        lines.append("%s：%s" % (cleaner.get_name(), "、".join(option_names)))
    return sorted(lines)
