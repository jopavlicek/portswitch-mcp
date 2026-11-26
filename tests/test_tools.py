"""Unit tests for PortSwitch MCP tools and safety-by-design gates."""

import os

from portswitch import server
from conftest import make_container


def test_check_conflicts_s1_named_volume_and_single_snapshot(monkeypatch, tmp_path):
    old_dir = str(tmp_path / "s1-old")
    cur_dir = str(tmp_path / "s1-current")

    old_db = make_container(
        cid="old-db-id",
        name="s1-old-db-1",
        compose_project="s1-old",
        working_dir=old_dir,
        host_ports=[5432],
        mounts=[{"Type": "volume", "Name": "s1-old_pgdata"}],
    )

    snapshot_calls = 0

    def fake_running():
        nonlocal snapshot_calls
        snapshot_calls += 1
        return [old_db]

    monkeypatch.setattr(server, "_project_ports", lambda path: [5432, 8080])
    monkeypatch.setattr(server, "_running_containers", fake_running)
    monkeypatch.setattr(server, "_is_free", lambda port: True)
    monkeypatch.setattr(server, "_same_repo", lambda a, b: False)

    res = server.check_conflicts(cur_dir)

    assert snapshot_calls == 1
    assert res["project"] == os.path.realpath(cur_dir)
    assert len(res["conflicts"]) == 1
    conflict = res["conflicts"][0]
    assert conflict["port"] == 5432
    assert conflict["container"] == "s1-old-db-1"
    assert conflict["compose_project"] == "s1-old"
    assert conflict["same_repo_worktree"] is False
    assert conflict["data"]["named_volumes"] == ["s1-old_pgdata"]
    assert "never use `down -v`" in conflict["advice"]
    assert os.path.realpath(old_dir) in server._identified_conflict_folders


def test_check_conflicts_s2_sibling_worktree(monkeypatch, tmp_path):
    wt_a = str(tmp_path / "s2-wt-a")
    wt_b = str(tmp_path / "s2-wt-b")

    containers = [
        make_container(cid="a-db", name="wt-a-db-1", compose_project="wt-a", working_dir=wt_a, host_ports=[5432]),
        make_container(cid="a-app", name="wt-a-app-1", compose_project="wt-a", working_dir=wt_a, host_ports=[3000]),
    ]

    monkeypatch.setattr(server, "_project_ports", lambda path: [3000, 5432])
    monkeypatch.setattr(server, "_running_containers", lambda: containers)
    monkeypatch.setattr(server, "_same_repo", lambda a, b: True)

    res = server.check_conflicts(wt_b)

    assert len(res["conflicts"]) == 2
    for conflict in res["conflicts"]:
        assert conflict["same_repo_worktree"] is True
        assert "Do not stop it" in conflict["advice"]


def test_check_conflicts_s3_anonymous_volume(monkeypatch, tmp_path):
    old_dir = str(tmp_path / "s3-old")
    cur_dir = str(tmp_path / "s3-current")
    anon_vol = "f" * 64

    old_db = make_container(
        cid="s3-db",
        name="s3-old-db-1",
        compose_project="s3-old",
        working_dir=old_dir,
        host_ports=[5432],
        mounts=[{"Type": "volume", "Name": anon_vol}],
    )

    monkeypatch.setattr(server, "_project_ports", lambda path: [5432])
    monkeypatch.setattr(server, "_running_containers", lambda: [old_db])
    monkeypatch.setattr(server, "_same_repo", lambda a, b: None)

    res = server.check_conflicts(cur_dir)

    assert len(res["conflicts"]) == 1
    assert res["conflicts"][0]["data"]["anonymous_volumes"] == [anon_vol]
    assert "anonymous volume" in res["conflicts"][0]["advice"]


def test_check_conflicts_ignores_own_project(monkeypatch, tmp_path):
    proj_dir = str(tmp_path / "my-proj")
    own = make_container(working_dir=proj_dir, host_ports=[5432])

    monkeypatch.setattr(server, "_project_ports", lambda path: [5432])
    monkeypatch.setattr(server, "_running_containers", lambda: [own])

    res = server.check_conflicts(proj_dir)
    assert res == {"project": os.path.realpath(proj_dir), "conflicts": []}
    assert server._identified_conflict_folders == set()


def test_check_conflicts_non_compose_and_external_process(monkeypatch, tmp_path):
    cur_dir = str(tmp_path / "current")
    plain = make_container(
        cid="plain-1",
        name="standalone-pg",
        compose_project=None,
        working_dir=None,
        host_ports=[5432],
    )

    monkeypatch.setattr(server, "_project_ports", lambda path: [5432, 3000])
    monkeypatch.setattr(server, "_running_containers", lambda: [plain])
    monkeypatch.setattr(server, "_is_free", lambda port: port != 3000)

    res = server.check_conflicts(cur_dir)

    assert len(res["conflicts"]) == 2
    assert "not started by docker compose" in res["conflicts"][0]["note"]
    assert "outside Docker" in res["conflicts"][1]["note"]
    assert server._identified_conflict_folders == set()


def test_check_conflicts_docker_error_returns_error_dict(monkeypatch, tmp_path):
    cur_dir = str(tmp_path / "empty")

    def fail_ports(path):
        raise server.DockerError("no configuration file provided")

    monkeypatch.setattr(server, "_project_ports", fail_ports)
    res = server.check_conflicts(cur_dir)
    assert res == {"project": os.path.realpath(cur_dir), "error": "no configuration file provided"}


def test_suggest_free_port_skips_docker_and_busy_ports(monkeypatch):
    monkeypatch.setattr(server, "_docker_published_ports", lambda: {5432})
    monkeypatch.setattr(server, "_is_free", lambda port: port != 5433)

    assert server.suggest_free_port(5432) == {"requested": 5432, "free_port": 5434}


def test_suggest_free_port_falls_back_when_docker_unreachable(monkeypatch):
    def fail_docker():
        raise server.DockerError("daemon not running")

    monkeypatch.setattr(server, "_docker_published_ports", fail_docker)
    monkeypatch.setattr(server, "_is_free", lambda port: port == 5432)

    assert server.suggest_free_port(5432) == {"requested": 5432, "free_port": 5432}


def test_suggest_free_port_validates_bounds():
    assert "error" in server.suggest_free_port(0)
    assert "error" in server.suggest_free_port(-5)
    assert "error" in server.suggest_free_port(65536)


def test_stop_project_refuses_unidentified_folder(monkeypatch, tmp_path):
    target = str(tmp_path / "unverified-project")
    ran_commands = []
    monkeypatch.setattr(server, "_run", lambda cmd, cwd=None: ran_commands.append(cmd) or "")

    res = server.stop_project(target)

    assert res["stopped"] == []
    assert "not identified as a conflicting project" in res["error"]
    assert ran_commands == []


def test_stop_project_stops_only_identified_compose_containers(monkeypatch, tmp_path):
    old_dir = str(tmp_path / "s1-old")
    cur_dir = str(tmp_path / "s1-current")

    old_containers = [
        make_container(cid="cid-1", name="s1-old-db-1", compose_project="s1-old", working_dir=old_dir, host_ports=[5432]),
        make_container(cid="cid-2", name="s1-old-worker-1", compose_project="s1-old", working_dir=old_dir, host_ports=[]),
    ]

    monkeypatch.setattr(server, "_project_ports", lambda path: [5432])
    monkeypatch.setattr(server, "_running_containers", lambda: old_containers)
    monkeypatch.setattr(server, "_same_repo", lambda a, b: False)

    # First identify the conflict via check_conflicts
    server.check_conflicts(cur_dir)

    ran_commands = []
    monkeypatch.setattr(server, "_run", lambda cmd, cwd=None: ran_commands.append(cmd) or "")

    res = server.stop_project(old_dir)

    assert ran_commands == [["docker", "stop", "cid-1", "cid-2"]]
    assert res["project_folder"] == os.path.realpath(old_dir)
    assert res["compose_project"] == "s1-old"
    assert res["stopped"] == ["s1-old-db-1", "s1-old-worker-1"]
    assert res["data_kept"] is True
    assert "docker compose start" in res["resume_with"]


def test_stop_project_idempotent_when_already_stopped(monkeypatch, tmp_path):
    old_dir = str(tmp_path / "s1-old")
    server._identified_conflict_folders.add(os.path.realpath(old_dir))
    monkeypatch.setattr(server, "_running_containers", lambda: [])

    res = server.stop_project(old_dir)
    assert res["stopped"] == []
    assert "Nothing was stopped" in res["note"]
