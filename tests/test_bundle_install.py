"""Tests for the Hugging Face-only bundle installer."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cli import main
from core.scripts import bundle_install


def test_install_bundle_requires_domain(capsys):
    assert bundle_install.install_bundle(check_only=True) == 1
    err = capsys.readouterr().err
    assert "published per domain" in err
    assert "--domain <name> or --auto" in err


def test_install_bundle_rejects_full_bundle(capsys):
    assert bundle_install.install_bundle(bundle_type="full", check_only=True, domain="linux") == 1
    err = capsys.readouterr().err
    assert "only publishes lite domain bundles" in err
    assert "local-build only" in err


def test_install_auto_rejects_full_bundle(capsys, tmp_path: Path):
    assert bundle_install.install_auto(bundle_type="full", check_only=True, project_dir=str(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "only publishes lite domain bundles" in err


def test_install_bundle_selects_requested_domain(monkeypatch, capsys):
    files = [
        "langskills-bundle-lite-web-v20260227.sqlite",
        "langskills-bundle-lite-web-v20260227.sqlite.sha256",
        "langskills-bundle-lite-programming-v20260227.sqlite",
        "langskills-bundle-lite-programming-v20260227.sqlite.sha256",
    ]

    monkeypatch.setattr(bundle_install, "_hf_list_files", lambda repo: files)
    monkeypatch.setenv("_HF_ACTIVE_ENDPOINT", "https://hf-mirror.com")

    assert bundle_install.install_bundle(domain="programming", check_only=True) == 0
    err = capsys.readouterr().err
    assert "Source: Hugging Face" in err
    assert "langskills-bundle-lite-programming-v20260227.sqlite" in err


def test_install_auto_detects_domains(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    calls: list[str] = []

    def fake_install_bundle(*, bundle_type: str, check_only: bool, domain: str) -> int:
        assert bundle_type == "lite"
        assert check_only is True
        calls.append(domain)
        return 0

    monkeypatch.setattr(bundle_install, "install_bundle", fake_install_bundle)

    assert bundle_install.install_auto(check_only=True, project_dir=str(tmp_path)) == 0
    assert calls == ["programming", "devtools"]


def test_cli_bundle_install_defaults_to_auto(monkeypatch, tmp_path):
    calls: dict[str, object] = {}

    def fake_install_auto(*, bundle_type: str, check_only: bool, project_dir: str) -> int:
        calls["bundle_type"] = bundle_type
        calls["check_only"] = check_only
        calls["project_dir"] = project_dir
        return 0

    monkeypatch.setattr(bundle_install, "install_auto", fake_install_auto)

    assert bundle_install.cli_bundle_install(["--check", "--project-dir", str(tmp_path)]) == 0
    assert calls == {
        "bundle_type": "lite",
        "check_only": True,
        "project_dir": str(tmp_path),
    }


def test_cli_bundle_install_help_hides_legacy_flags(capsys):
    with pytest.raises(SystemExit) as excinfo:
        bundle_install.cli_bundle_install(["--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Hugging Face" in out
    assert "--source" not in out
    assert "--repo" not in out
    assert "--release" not in out


def test_main_bundle_install_dispatches_hf_only_args(monkeypatch):
    calls: dict[str, list[str] | None] = {}

    def fake_cli_bundle_install(argv: list[str] | None = None) -> int:
        calls["argv"] = argv
        return 0

    monkeypatch.setattr(bundle_install, "cli_bundle_install", fake_cli_bundle_install)

    assert main(["bundle-install", "--bundle", "lite", "--check", "--domain", "linux"]) == 0
    assert calls["argv"] == ["--bundle", "lite", "--check", "--domain", "linux"]


def test_main_bundle_install_help_hides_legacy_flags(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["bundle-install", "--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Hugging Face" in out
    assert "--repo" not in out
    assert "--release" not in out


def test_install_auto_reports_unrecognized_project(capsys, tmp_path: Path):
    assert bundle_install.install_auto(check_only=True, project_dir=str(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "No recognizable project type detected" in err
    assert "Use --domain to specify manually." in err
