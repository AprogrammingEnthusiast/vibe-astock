from pathlib import Path

import pytest

import sharing
import sharing_admin


def test_single_application_manifest():
    config = sharing_admin.manifest(18910, False)
    assert list(config["services"]) == ["gateway"]
    service = config["services"]["gateway"]
    assert service["environment"]["VIBE_SHARED_APP"] == "1"
    assert service["environment"]["VIBE_COOKIE_SECURE"] == "0"
    assert service["ports"] == ["127.0.0.1:18910:8910"]
    assert service["volumes"] == ["accounts:/home/app/sharing"]
    assert "env_file" not in service
    assert service["read_only"]


def test_import_home_preserves_source_and_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing, "DB", tmp_path / "accounts.sqlite3")
    sharing.initialize()
    sharing_admin.provision("alice", owner=True)
    with sharing.connect() as db:
        row = db.execute("SELECT * FROM users WHERE username='alice'").fetchone()
    assert row["worker"] == ""
    assert row["worker_key"]
    sharing_admin.provision("bobby")
    source = tmp_path / "legacy"
    source.mkdir()
    (source / ".codex").mkdir()
    original = source / ".codex" / "auth.json"
    original.write_bytes(b"test-only-secret")
    before = original.stat().st_mtime_ns
    target = sharing_admin.import_home("alice", source)
    assert target == tmp_path / "homes" / row["id"]
    assert (target / ".codex" / "auth.json").read_bytes() == original.read_bytes()
    assert original.stat().st_mtime_ns == before
    with pytest.raises(ValueError, match="已存在"):
        sharing_admin.import_home("alice", source)
    assert not list(target.parent.glob(".import-*"))


def test_import_home_rejects_unknown_and_cleans_failed_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing, "DB", tmp_path / "accounts.sqlite3")
    sharing.initialize()
    source = tmp_path / "legacy"
    source.mkdir()
    with pytest.raises(ValueError, match="账号不存在"):
        sharing_admin.import_home("missing", source)
    sharing_admin.provision("alice")
    def fail_copy(src, dst, **kwargs):
        Path(dst).mkdir()
        (Path(dst) / "partial").write_text("incomplete")
        raise OSError("test disk failure")
    monkeypatch.setattr(sharing_admin.shutil, "copytree", fail_copy)
    with pytest.raises(OSError):
        sharing_admin.import_home("alice", source)
    assert list((tmp_path / "homes").iterdir()) == []
    assert source.is_dir()


def test_import_home_rejects_links(tmp_path, monkeypatch):
    monkeypatch.setattr(sharing, "DB", tmp_path / "accounts.sqlite3")
    sharing.initialize()
    sharing_admin.provision("alice")
    source = tmp_path / "legacy"
    source.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    link = source / "link"
    try:
        link.symlink_to(other, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires platform permission")
    with pytest.raises(ValueError, match="链接"):
        sharing_admin.import_home("alice", source)
    with pytest.raises(ValueError, match="链接"):
        sharing_admin.import_home("alice", link)
    assert not (tmp_path / "homes").exists()
