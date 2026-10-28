# TestDuplicateFinder.py / TestDiskAnalyzer.py -- GTK-free logic tests.
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bleachbit.DuplicateFinder import scan_duplicates  # noqa: E402
from bleachbit.DiskAnalyzer import scan_dir_sizes  # noqa: E402


def _make_tree(tmp):
    """tmp/{d1/A.bin, d2/A2.bin, d2/B.bin} with A dup of A2 (2KB), B unique"""
    d1 = os.path.join(tmp, "d1")
    d2 = os.path.join(tmp, "d2")
    os.makedirs(d1)
    os.makedirs(os.path.join(d2, "sub"))
    content = b"x" * 2048
    open(os.path.join(d1, "A.bin"), "wb").write(content)
    open(os.path.join(d2, "A2.bin"), "wb").write(content)
    open(os.path.join(d2, "B.bin"), "wb").write(b"unique" * 7)
    open(os.path.join(d2, "sub", "A3.bin"), "wb").write(content)
    open(os.path.join(d2, "empty.bin"), "wb").write(b"")
    return d1, d2


class TestDuplicateFinder:
    def test_finds_cross_dir_duplicates(self, tmp_path):
        _make_tree(str(tmp_path))
        groups = scan_duplicates([str(tmp_path)])
        dup_paths = sorted(p for g in groups for p in g["paths"])
        assert len(groups) == 1
        assert groups[0]["size"] == 2048
        assert len(dup_paths) == 3
        assert any(p.endswith("A.bin") for p in dup_paths)
        assert any(p.endswith("A3.bin") for p in dup_paths)
        assert not any("B.bin" in p for p in dup_paths)
        assert not any("empty" in p for p in dup_paths)

    def test_stop_flag_returns_partial(self, tmp_path):
        groups = scan_duplicates([str(tmp_path)], should_continue=lambda: False)
        assert groups == []

    def test_missing_root_is_tolerated(self, tmp_path):
        _make_tree(str(tmp_path))
        groups = scan_duplicates([str(tmp_path / "nope"), str(tmp_path)])
        assert groups


class TestDiskAnalyzer:
    def test_sizes_aggregate_to_ancestors(self, tmp_path):
        d1, d2 = _make_tree(str(tmp_path))
        results = dict(scan_dir_sizes(str(tmp_path)))
        root_total = results[os.path.normcase(
            os.path.abspath(str(tmp_path)))]
        assert root_total == 2048 * 3 + 42  # three dup files + B.bin
        sub_total = results[os.path.normcase(
            os.path.abspath(os.path.join(d2, "sub")))]
        assert sub_total == 2048

    def test_stop_flag(self, tmp_path):
        results = scan_dir_sizes(str(tmp_path), should_continue=lambda: False)
        assert isinstance(results, list)
