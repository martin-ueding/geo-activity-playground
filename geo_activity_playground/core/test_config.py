import json
import os
import pathlib

from .config import ConfigAccessor


def _write_config(path: pathlib.Path, mtime_ns: int, **fields) -> None:
    path.write_text(json.dumps(fields))
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_reloads_when_file_changed_on_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.json"

    _write_config(config_path, 1_000_000_000, search_map_tiles_per_page=10)
    accessor = ConfigAccessor()
    assert accessor().search_map_tiles_per_page == 10

    # Simulate another process writing a newer config.
    _write_config(config_path, 2_000_000_000, search_map_tiles_per_page=42)
    assert accessor().search_map_tiles_per_page == 42


def test_does_not_reload_when_mtime_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.json"

    _write_config(config_path, 1_000_000_000, search_map_tiles_per_page=10)
    accessor = ConfigAccessor()

    # Change contents but keep the same mtime: the accessor must not reload.
    _write_config(config_path, 1_000_000_000, search_map_tiles_per_page=42)
    assert accessor().search_map_tiles_per_page == 10


def test_save_does_not_trigger_reload_of_own_write(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    accessor = ConfigAccessor()
    accessor().search_map_tiles_per_page = 7
    accessor.save()
    # A subsequent access must keep the in-memory value we just saved.
    assert accessor().search_map_tiles_per_page == 7
