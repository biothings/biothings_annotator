"""Local version fallback identifies the checkout loaded at application startup."""

import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from sanic import Sanic

import biothings_annotator.application as application_module
from biothings_annotator.application import build_application
from biothings_annotator.application import version as local_version
from biothings_annotator.application.cli.arguments import load_configuration
from biothings_annotator.application.views.metadata import VersionView


pytestmark = pytest.mark.unit


def git(checkout: Path, *arguments: str) -> str:
    """Use only temporary repositories, without depending on a user's Git identity."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "user.name=Version Test",
            "-c",
            "user.email=version-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
        env=environment,
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("Git is required to exercise a real temporary checkout")
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "--quiet")
    (root / "source.py").write_text("VERSION = 1\n", encoding="utf-8")
    git(root, "add", "source.py")
    git(root, "commit", "--quiet", "-m", "Initial source")
    monkeypatch.setattr(local_version, "SOURCE_ROOT", root)
    return root


@pytest.fixture
def application_configuration(monkeypatch):
    monkeypatch.setattr(Sanic, "_app_registry", {})
    monkeypatch.delenv("ANNOTATOR_DEPLOYMENT_ENV", raising=False)
    monkeypatch.setenv("ANNOTATOR_QUERY_BACKEND", "elasticsearch")
    monkeypatch.setenv("ELASTICSEARCH_CONNECTION", "ci_forward")
    configuration = load_configuration()
    configuration["application"]["telemetry"]["OPENTELEMETRY_ENABLED"] = False
    return configuration


@pytest.mark.parametrize("state", ["clean", "modified", "staged", "untracked"])
def test_checkout_version_marks_tracked_and_untracked_changes(checkout, state):
    commit = git(checkout, "rev-parse", "HEAD")
    assert len(commit) == 40
    if state in {"modified", "staged"}:
        (checkout / "source.py").write_text("VERSION = 2\n", encoding="utf-8")
        if state == "staged":
            git(checkout, "add", "source.py")
    elif state == "untracked":
        # Explicit inclusion must win over a checkout configured to hide these.
        git(checkout, "config", "status.showUntrackedFiles", "no")
        (checkout / "new_source.py").write_text("NEW = True\n", encoding="utf-8")

    assert local_version.get_local_git_version() == commit + ("" if state == "clean" else "-dirty")


def test_checkout_version_ignores_launch_directory_and_inherited_git_overrides(checkout, tmp_path, monkeypatch):
    expected = git(checkout, "rev-parse", "HEAD")
    launch_directory = tmp_path / "elsewhere"
    launch_directory.mkdir()
    monkeypatch.chdir(launch_directory)
    monkeypatch.setenv("GIT_DIR", str(launch_directory / "different.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(launch_directory))
    monkeypatch.setenv("GIT_INDEX_FILE", str(launch_directory / "different-index"))

    assert local_version.get_local_git_version() == expected
    assert not list(launch_directory.iterdir())


def test_checkout_version_supports_git_worktree_files(checkout, tmp_path, monkeypatch):
    expected = git(checkout, "rev-parse", "HEAD")
    worktree = tmp_path / "worktree"
    git(checkout, "worktree", "add", "--quiet", "--detach", str(worktree), "HEAD")
    assert (worktree / ".git").is_file()
    monkeypatch.setattr(local_version, "SOURCE_ROOT", worktree)

    assert local_version.get_local_git_version() == expected


def test_package_without_own_git_directory_does_not_borrow_parent_checkout(checkout, monkeypatch):
    nested_package = checkout / "installed-package"
    nested_package.mkdir()
    monkeypatch.setattr(local_version, "SOURCE_ROOT", nested_package)
    runner = Mock(side_effect=AssertionError("Git must not inspect an enclosing repository"))
    monkeypatch.setattr(local_version.subprocess, "run", runner)

    assert local_version.get_local_git_version() == "Unknown"
    runner.assert_not_called()


@pytest.mark.parametrize("failure", ["missing_git", "failed_command", "timeout"])
def test_git_failures_report_unknown(tmp_path, monkeypatch, failure):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(local_version, "SOURCE_ROOT", tmp_path)
    errors = {
        "missing_git": FileNotFoundError("git unavailable"),
        "failed_command": subprocess.CalledProcessError(128, ["git"]),
        "timeout": subprocess.TimeoutExpired(["git"], 2),
    }
    runner = Mock(side_effect=errors[failure])
    monkeypatch.setattr(local_version.subprocess, "run", runner)

    assert local_version.get_local_git_version() == "Unknown"
    assert runner.call_args.kwargs["timeout"] == 2
    assert runner.call_args.kwargs["check"] is True


def test_status_failure_does_not_report_a_commit_as_clean(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(local_version, "SOURCE_ROOT", tmp_path)
    runner = Mock(
        side_effect=[
            subprocess.CompletedProcess(["git"], 0, stdout="a" * 40 + "\n"),
            subprocess.CalledProcessError(128, ["git", "status"]),
        ]
    )
    monkeypatch.setattr(local_version.subprocess, "run", runner)

    assert local_version.get_local_git_version() == "Unknown"
    assert runner.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["unknown", "ci", "test", "prod", "Local"])
async def test_nonlocal_version_never_inspects_git_and_retains_caching(
    application_configuration, tmp_path, monkeypatch, environment
):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = environment
    snapshot = Mock(side_effect=AssertionError("Only explicitly local deployments may inspect Git"))
    monkeypatch.setattr(application_module, "get_local_git_version", snapshot)
    monkeypatch.chdir(tmp_path)
    application = build_application(application_configuration)

    _, response = await application.asgi_client.get("/version")

    snapshot.assert_not_called()
    assert response.status_code == 200
    assert response.json["version"] == "Unknown"
    assert response.headers["Cache-Control"] == f"max-age={application.config.CACHE_MAX_AGE}, public"


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["local", " local "])
async def test_local_missing_version_file_uses_startup_snapshot(
    application_configuration, tmp_path, monkeypatch, environment
):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = environment
    snapshot_version = "a" * 40 + "-dirty"
    snapshot = Mock(return_value=snapshot_version)
    monkeypatch.setattr(application_module, "get_local_git_version", snapshot)
    monkeypatch.chdir(tmp_path)
    application = build_application(application_configuration)

    _, response = await application.asgi_client.get("/version")
    _, repeated = await application.asgi_client.get("/version/")

    snapshot.assert_called_once_with()
    assert application.ctx.local_git_version == snapshot_version
    assert response.status_code == repeated.status_code == 200
    assert response.json == repeated.json == {
        "version": snapshot_version,
        "query_backend": "elasticsearch",
        "elasticsearch_connection": "ci_forward",
    }
    assert response.headers["Cache-Control"] == repeated.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_version_file_takes_precedence_over_local_snapshot(application_configuration, tmp_path, monkeypatch):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = "local"
    monkeypatch.setattr(application_module, "get_local_git_version", Mock(return_value="a" * 40 + "-dirty"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "version.txt").write_text("deployed-version\n", encoding="utf-8")
    application = build_application(application_configuration)

    _, response = await application.asgi_client.get("/version")

    assert response.json["version"] == "deployed-version"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("read_error", [PermissionError("unreadable file"), UnicodeError("invalid contents")])
async def test_local_version_read_errors_do_not_use_git_fallback(
    application_configuration, monkeypatch, read_error
):
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = "local"
    monkeypatch.setattr(application_module, "get_local_git_version", Mock(return_value="a" * 40 + "-dirty"))
    monkeypatch.setattr(VersionView, "open_version_file", Mock(side_effect=read_error))
    application = build_application(application_configuration)

    _, response = await application.asgi_client.get("/version")

    assert response.json["version"] == "Unknown"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_running_application_keeps_snapshot_after_checkout_head_changes(
    checkout, application_configuration, tmp_path, monkeypatch
):
    original_commit = git(checkout, "rev-parse", "HEAD")
    application_configuration["application"]["configuration"]["DEPLOYMENT_ENVIRONMENT"] = "local"
    monkeypatch.chdir(tmp_path)
    application = build_application(application_configuration)
    git(checkout, "commit", "--quiet", "--allow-empty", "-m", "A commit made after startup")
    assert git(checkout, "rev-parse", "HEAD") != original_commit
    snapshot = Mock(side_effect=AssertionError("Requests must not inspect a newer checkout"))
    monkeypatch.setattr(application_module, "get_local_git_version", snapshot)
    monkeypatch.setattr(local_version, "get_local_git_version", snapshot)

    _, response = await application.asgi_client.get("/version")

    assert application.ctx.local_git_version == original_commit
    assert response.json["version"] == original_commit
    snapshot.assert_not_called()
