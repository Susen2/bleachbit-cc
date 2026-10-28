# SPDX-License-Identifier: GPL-3.0-or-later
# Disk usage analysis logic. GTK-free.

import os


def scan_dir_sizes(root, progress_cb=None, should_continue=None):
    """Return [(dir_path, total_bytes), ...] for every directory under
    `root` (inclusive), sorted largest first.

    progress_cb(dirs_done) fires periodically; should_continue() False
    stops early and returns the partial result.
    """
    if progress_cb is None:
        progress_cb = lambda *a: None
    if should_continue is None:
        should_continue = lambda: True

    sizes = {}
    done = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if not should_continue():
            break
        total = 0
        for fn in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                continue
        sizes[dirpath] = sizes.get(dirpath, 0) + total
        done += 1
        if done % 50 == 0:
            progress_cb(done)
            if not should_continue():
                break

    if not should_continue():
        return _aggregate(sizes)

    # roll sizes up to ancestors
    for dirpath in list(sizes):
        parent = os.path.dirname(dirpath)
        while parent and parent.startswith(os.path.abspath(root)):
            sizes[parent] = sizes.get(parent, 0)
            parent = os.path.dirname(parent)
    return _aggregate(sizes)


def _aggregate(sizes):
    """Roll each directory's own size up to all its ancestors."""
    result = {}
    normalized = {os.path.normcase(os.path.abspath(k)): v
                  for k, v in sizes.items()}
    for path, own_size in normalized.items():
        result[path] = result.get(path, 0)
        result[path] += own_size
        # propagate to ancestors that are in the map
        parts = path.split(os.sep)
        for i in range(len(parts) - 1, 0, -1):
            ancestor = os.sep.join(parts[:i])
            if ancestor in normalized:
                result[ancestor] = result.get(ancestor, 0) + own_size
    return sorted(result.items(), key=lambda kv: kv[1], reverse=True)
