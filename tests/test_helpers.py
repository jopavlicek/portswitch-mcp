"""Unit tests for internal helper functions in portswitch.server."""

import os
import subprocess

from portswitch import server
from conftest import make_compose_config, make_container


def test_is_anonymous_volume():
    anon = "a" * 64
    assert server._is_anonymous_volume(anon) is True
    assert server._is_anonymous_volume("0123456789abcdef" * 4) is True
    assert server._is_anonymous_volume("pgdata") is False
    assert server._is_anonymous_volume("g" * 64) is False
    assert server._is_anonymous_volume("a" * 63) is False


def test_project_ports_deduplicates_and_ignores_non_numeric(monkeypatch):
    payload = make_compose_config(5432, 8080, 5432, "", "8000-8005")
    monkeypatch.setattr(server, "_run", lambda cmd, cwd=None: payload)

    assert server._project_ports("/work/current") == [5432, 8080]


def test_owner_matches_host_port_from_snapshot():
    c = make_container(
        name="s1-old-db-1",
        compose_project="s1-old",
        working_dir="/work/s1-old",
        host_ports=[5432],
    )
    owner = server._owner(5432, containers=[c])
    assert owner == {
        "container": "s1-old-db-1",
        "compose_project": "s1-old",
        "project_folder": "/work/s1-old",
    }
    assert server._owner(3000, containers=[c]) is None


def test_project_data_classifies_volumes_and_binds(tmp_path):
    folder = str(tmp_path / "proj")
    anon_id = "3f9c" * 16
    containers = [
        make_container(
            cid="c1",
            name="proj-db-1",
            working_dir=folder,
            mounts=[
                {"Type": "volume", "Name": "proj_pgdata"},
                {"Type": "volume", "Name": anon_id},
            ],
        ),
        make_container(
            cid="c2",
            name="proj-app-1",
            working_dir=folder,
            mounts=[
                {"Type": "bind", "Source": "/work/proj/app"},
            ],
        ),
        make_container(
            cid="c3",
            name="other-db-1",
            working_dir=str(tmp_path / "other"),
            mounts=[{"Type": "volume", "Name": "other_vol"}],
        ),
    ]

    data = server._project_data(folder, containers=containers)
    assert data == {
        "named_volumes": ["proj_pgdata"],
        "anonymous_volumes": [anon_id],
        "bind_mounts": ["/work/proj/app"],
    }


def test_advice_branches():
    empty = {"named_volumes": [], "anonymous_volumes": [], "bind_mounts": []}
    named = {"named_volumes": ["pgdata"], "anonymous_volumes": [], "bind_mounts": []}
    anon = {"named_volumes": [], "anonymous_volumes": ["a" * 64], "bind_mounts": []}

    assert "worktree" in server._advice(True, anon)
    assert "suggest_free_port" in server._advice(True, empty)
    assert "anonymous volume" in server._advice(False, anon)
    assert "named volumes" in server._advice(False, named)
    assert "No volumes found" in server._advice(None, empty)


def test_docker_published_ports(monkeypatch):
    containers = [
        make_container(cid="c1", host_ports=[5432]),
        make_container(cid="c2", host_ports=[3000, 8080]),
    ]
    monkeypatch.setattr(server, "_running_containers", lambda: containers)
    assert server._docker_published_ports() == {3000, 5432, 8080}


def test_same_repo_compares_git_common_dir(monkeypatch, tmp_path):
    a = str(tmp_path / "wt-a")
    b = str(tmp_path / "wt-b")
    c = str(tmp_path / "other")
    shared_git = os.path.realpath(str(tmp_path / "repo.git"))

    def fake_common_dir(path: str) -> str | None:
        if path in (a, b):
            return shared_git
        if path == c:
            return os.path.realpath(str(tmp_path / "other.git"))
        return None

    monkeypatch.setattr(server, "_git_common_dir", fake_common_dir)
    assert server._same_repo(a, b) is True
    assert server._same_repo(a, c) is False
    assert server._same_repo(a, str(tmp_path / "missing")) is None


def test_git_common_dir_handles_errors(monkeypatch, tmp_path):
    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(subprocess, "run", raise_called_process_error)
    assert server._git_common_dir(str(tmp_path)) is None
