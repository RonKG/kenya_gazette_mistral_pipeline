from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

import gazette_mistral_pipeline as gmp

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "install_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("install_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_public_name_contract_matches_package_root() -> None:
    smoke = _load_smoke_module()

    for name in smoke.REQUIRED_PUBLIC_NAMES:
        assert hasattr(gmp, name)
        assert name in gmp.__all__


def test_smoke_helpers_are_windows_and_offline_friendly() -> None:
    smoke = _load_smoke_module()

    assert smoke.venv_python_path(Path("venv"), os_name="nt") == Path("venv") / "Scripts" / "python.exe"
    assert smoke.venv_python_path(Path("venv"), os_name="posix") == Path("venv") / "bin" / "python"

    env = smoke.clean_subprocess_env(
        {
            "MISTRAL_API_KEY": "secret",
            "PYTHONPATH": str(ROOT),
            "PYTHONHOME": "python-home",
            "KEEP_ME": "1",
        }
    )
    assert "MISTRAL_API_KEY" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert env["KEEP_ME"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"


def test_git_url_mode_skips_without_explicit_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    smoke = _load_smoke_module()
    monkeypatch.delenv("F12_GIT_URL", raising=False)

    result = smoke.main(["--repo-path", str(ROOT), "--mode", "git-url"])

    assert result == 0
    assert "SKIP: git-url smoke requires" in capsys.readouterr().out


def test_installed_check_code_contains_offline_replay_flow() -> None:
    smoke = _load_smoke_module()

    code = smoke.installed_check_code()

    assert "parse_url(" in code
    assert "replay_raw_json_path" in code
    assert "write_envelope" in code
    assert "validate_envelope_json" in code
    assert "MISTRAL_API_KEY" in code


@pytest.mark.smoke
@pytest.mark.skipif(
    os.environ.get("F12_RUN_INSTALL_SMOKE") != "1",
    reason="set F12_RUN_INSTALL_SMOKE=1 to run the full fresh-venv smoke from pytest",
)
def test_install_smoke_script_local_path() -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--repo-path", str(ROOT), "--mode", "local-path"],
        cwd=ROOT,
        check=True,
    )
