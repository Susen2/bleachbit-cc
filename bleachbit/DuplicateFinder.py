# SPDX-License-Identifier: GPL-3.0-or-later
# Duplicate file finder logic. GTK-free.

import hashlib
import os

CHUNK = 1024 * 1024
MIN_SIZE = 1  # ignore empty files


def _file_hash(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def scan_duplicates(roots, progress_cb=None, should_continue=None):
    """Find duplicate files under `roots`.

    Returns a list of groups sorted by wasted size (largest first):
        [{"size": int, "hash": str, "paths": [str, ...]}, ...]

    progress_cb(done_files, found_groups) is called periodically.
    should_continue() returning False stops the scan early; the partial
    result is returned.
    """
    if progress_cb is None:
        progress_cb = lambda *a: None
    if should_continue is None:
        should_continue = lambda: True

    by_size = {}
    done = 0
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if not should_continue():
                break
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                try:
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size < MIN_SIZE:
                    continue
                by_size.setdefault(size, []).append(path)
                done += 1
                if done % 200 == 0:
                    progress_cb(done, 0)
                    if not should_continue():
                        break
            if not should_continue():
                break
        if not should_continue():
            break

    groups = []
    for size, paths in by_size.items():
        if not should_continue():
            break
        if len(paths) < 2:
            continue
        by_hash = {}
        for path in paths:
            try:
                by_hash.setdefault(_file_hash(path), []).append(path)
            except OSError:
                continue
            if not should_continue():
                break
        for digest, dup_paths in by_hash.items():
            if len(dup_paths) > 1:
                groups.append({"size": size, "hash": digest,
                               "paths": dup_paths})
        progress_cb(done, len(groups))

    groups.sort(key=lambda g: g["size"] * (len(g["paths"]) - 1),
                reverse=True)
    return groups
