"""Fresh-environment install smoke for gazette_mistral_pipeline.

The default mode is offline-friendly: it installs the local project without
downloading dependencies and relies on the invoking Python's site packages for
already-installed runtime dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import zipfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

DIST_NAME = "gazette-mistral-pipeline"
PACKAGE_NAME = "gazette_mistral_pipeline"

REQUIRED_PUBLIC_NAMES = [
    "parse_file",
    "parse_url",
    "parse_source",
    "write_envelope",
    "get_envelope_schema",
    "validate_envelope_json",
    "Envelope",
    "PdfSource",
    "MistralMetadata",
    "Notice",
    "ExtractedTable",
    "Corrigendum",
    "ConfidenceScores",
    "Provenance",
    "Stats",
    "LayoutInfo",
    "DocumentConfidence",
    "PipelineWarning",
    "Bundles",
    "GazetteConfig",
    "MistralOptions",
    "RuntimeOptions",
]

EXPECTED_RUNTIME_REQUIRES = ["pydantic>=2.0"]
EXCLUDED_DISTRIBUTION_PREFIXES = ("docs/", "specs/", "tests/", "prototype_outputs/")
EXCLUDED_DISTRIBUTION_NAMES = {".env"}
EXCLUDED_DISTRIBUTION_SUFFIXES = (".ipynb",)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Local repository path to install. Defaults to this script's repository.",
    )
    parser.add_argument(
        "--mode",
        choices=["local-path", "wheel", "git-url"],
        default="local-path",
        help="Install source to smoke. Git URL mode skips unless a URL is supplied.",
    )
    parser.add_argument(
        "--git-url",
        default=os.environ.get("F12_GIT_URL"),
        help="Explicit Git URL for optional git-url mode. Defaults to F12_GIT_URL.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory for temporary venv/check files. Created if missing.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve the generated temp directory for debugging.",
    )
    parser.add_argument(
        "--dependency-mode",
        choices=["offline-no-deps", "pip"],
        default="offline-no-deps",
        help=(
            "offline-no-deps avoids dependency downloads with --no-deps and "
            "--no-build-isolation. pip lets pip resolve dependencies normally."
        ),
    )
    parser.add_argument(
        "--skip-wheel-check",
        action="store_true",
        help="Skip wheel build/content inspection in local-path mode.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_path = args.repo_path.resolve()

    if args.mode == "git-url" and not args.git_url:
        print("SKIP: git-url smoke requires --git-url or F12_GIT_URL.")
        return 0

    if args.mode != "git-url":
        assert_repo_path(repo_path)

    if args.work_dir is None:
        with tempfile.TemporaryDirectory(prefix="gmp-install-smoke-") as tmp:
            return run_smoke(args, repo_path=repo_path, temp_root=Path(tmp))

    temp_root = args.work_dir.resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        return run_smoke(args, repo_path=repo_path, temp_root=temp_root)
    finally:
        if args.keep_temp:
            print(f"Kept smoke work directory: {temp_root}")


def run_smoke(argparse_args: argparse.Namespace, *, repo_path: Path, temp_root: Path) -> int:
    temp_root = temp_root.resolve()
    assert_outside_repo(temp_root, repo_path)

    pyproject = load_pyproject(repo_path) if argparse_args.mode != "git-url" else {}
    venv_dir = temp_root / "venv"
    check_dir = temp_root / "installed-check"
    wheel_dir = temp_root / "wheelhouse"
    check_dir.mkdir(parents=True, exist_ok=True)

    create_venv(
        venv_dir,
        system_site_packages=argparse_args.dependency_mode == "offline-no-deps",
    )
    python = venv_python_path(venv_dir)
    env = clean_subprocess_env(os.environ)

    wheel_path: Path | None = None
    if argparse_args.mode == "wheel":
        wheel_path = build_wheel(python, repo_path, wheel_dir, env=env)
        inspect_wheel(wheel_path)
        install_target = wheel_path
    elif argparse_args.mode == "git-url":
        install_target = argparse_args.git_url
    else:
        install_target = repo_path

    install_package(
        python,
        install_target,
        dependency_mode=argparse_args.dependency_mode,
        cwd=check_dir,
        env=env,
    )

    if argparse_args.mode == "local-path" and not argparse_args.skip_wheel_check:
        wheel_path = build_wheel(python, repo_path, wheel_dir, env=env)
        inspect_wheel(wheel_path)

    run_installed_checks(
        python,
        work_dir=check_dir,
        repo_path=repo_path,
        pyproject=pyproject,
        env=env,
    )
    print("F12 install smoke passed.")
    return 0


def assert_repo_path(repo_path: Path) -> None:
    pyproject_path = repo_path / "pyproject.toml"
    package_dir = repo_path / PACKAGE_NAME
    if not pyproject_path.is_file() or not package_dir.is_dir():
        raise FileNotFoundError(f"{repo_path} does not look like the repository root.")


def assert_outside_repo(path: Path, repo_path: Path) -> None:
    try:
        path.relative_to(repo_path)
    except ValueError:
        return
    raise ValueError(f"smoke work directory must be outside the repository: {path}")


def load_pyproject(repo_path: Path) -> dict[str, object]:
    return tomllib.loads((repo_path / "pyproject.toml").read_text(encoding="utf-8"))


def create_venv(venv_dir: Path, *, system_site_packages: bool) -> None:
    command = [sys.executable, "-m", "venv"]
    if system_site_packages:
        command.append("--system-site-packages")
    command.append(str(venv_dir))
    run(command, cwd=venv_dir.parent)


def venv_python_path(venv_dir: Path, *, os_name: str | None = None) -> Path:
    selected_os = os_name or os.name
    if selected_os == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def clean_subprocess_env(source: Mapping[str, str]) -> dict[str, str]:
    env = dict(source)
    for key in ["MISTRAL_API_KEY", "PYTHONPATH", "PYTHONHOME"]:
        env.pop(key, None)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def install_package(
    python: Path,
    target: str | Path,
    *,
    dependency_mode: str,
    cwd: Path,
    env: Mapping[str, str],
) -> None:
    command = [str(python), "-m", "pip", "install", "--ignore-installed"]
    if dependency_mode == "offline-no-deps":
        command.extend(["--no-deps", "--no-build-isolation"])
    command.append(str(target))
    run(command, cwd=cwd, env=env)


def build_wheel(
    python: Path,
    repo_path: Path,
    wheel_dir: Path,
    *,
    env: Mapping[str, str],
) -> Path:
    wheel_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(repo_path),
        ],
        cwd=wheel_dir,
        env=env,
    )
    wheels = sorted(wheel_dir.glob("gazette_mistral_pipeline-*.whl"))
    if not wheels:
        raise FileNotFoundError(f"no wheel was built under {wheel_dir}")
    return wheels[-1]


def inspect_wheel(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    require_wheel_member(names, f"{PACKAGE_NAME}/__init__.py")
    require_wheel_member(names, f"{PACKAGE_NAME}/py.typed")
    require_wheel_member(names, f"{PACKAGE_NAME}/schemas/envelope.schema.json")
    assert_no_excluded_distribution_files(names, source=f"wheel {wheel_path.name}")


def require_wheel_member(names: set[str], member: str) -> None:
    if member not in names:
        raise AssertionError(f"wheel is missing expected package file: {member}")


def run_installed_checks(
    python: Path,
    *,
    work_dir: Path,
    repo_path: Path,
    pyproject: Mapping[str, object],
    env: Mapping[str, str],
) -> None:
    check_script = work_dir / "f12_installed_checks.py"
    check_script.write_text(installed_check_code(), encoding="utf-8")

    project = pyproject.get("project", {}) if pyproject else {}
    check_env = dict(env)
    check_env.update(
        {
            "F12_REPO_PATH": str(repo_path),
            "F12_EXPECTED_VERSION": str(project.get("version", "")),
            "F12_EXPECTED_REQUIRES_PYTHON": str(project.get("requires-python", "")),
            "F12_EXPECTED_LICENSE": str(project.get("license", {}).get("text", "")),
            "F12_REQUIRED_PUBLIC_NAMES": json.dumps(REQUIRED_PUBLIC_NAMES),
            "F12_EXPECTED_RUNTIME_REQUIRES": json.dumps(EXPECTED_RUNTIME_REQUIRES),
            "F12_EXCLUDED_PREFIXES": json.dumps(EXCLUDED_DISTRIBUTION_PREFIXES),
            "F12_EXCLUDED_NAMES": json.dumps(sorted(EXCLUDED_DISTRIBUTION_NAMES)),
            "F12_EXCLUDED_SUFFIXES": json.dumps(EXCLUDED_DISTRIBUTION_SUFFIXES),
        }
    )
    run([str(python), str(check_script)], cwd=work_dir, env=check_env)


def installed_check_code() -> str:
    return textwrap.dedent(
        r'''
        from __future__ import annotations

        import json
        import os
        import sys
        from importlib import metadata, resources
        from pathlib import Path

        DIST_NAME = "gazette-mistral-pipeline"
        PACKAGE_NAME = "gazette_mistral_pipeline"
        KENYALAW_URL = (
            "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
            "eng@2026-04-17/source.pdf"
        )

        def main() -> None:
            repo_path = Path(os.environ["F12_REPO_PATH"]).resolve()
            if Path.cwd().resolve() == repo_path:
                raise AssertionError("installed checks must not run from the repository root")
            if str(repo_path) in sys.path:
                raise AssertionError("repository path leaked into sys.path")
            if os.environ.get("MISTRAL_API_KEY"):
                raise AssertionError("MISTRAL_API_KEY must not be required for the smoke")

            required_public_names = json.loads(os.environ["F12_REQUIRED_PUBLIC_NAMES"])
            expected_runtime_requires = json.loads(os.environ["F12_EXPECTED_RUNTIME_REQUIRES"])
            excluded_prefixes = tuple(json.loads(os.environ["F12_EXCLUDED_PREFIXES"]))
            excluded_names = set(json.loads(os.environ["F12_EXCLUDED_NAMES"]))
            excluded_suffixes = tuple(json.loads(os.environ["F12_EXCLUDED_SUFFIXES"]))

            import gazette_mistral_pipeline as gmp
            from gazette_mistral_pipeline import Bundles, GazetteConfig

            dist_version = metadata.version(DIST_NAME)
            expected_version = os.environ["F12_EXPECTED_VERSION"]
            if expected_version:
                assert dist_version == expected_version
            assert gmp.__version__ == dist_version

            dist_metadata = metadata.metadata(DIST_NAME)
            assert dist_metadata["Name"] == DIST_NAME
            expected_requires_python = os.environ["F12_EXPECTED_REQUIRES_PYTHON"]
            if expected_requires_python:
                assert dist_metadata["Requires-Python"] == expected_requires_python
            expected_license = os.environ["F12_EXPECTED_LICENSE"]
            if expected_license:
                assert dist_metadata["License"] == expected_license

            requirements = metadata.requires(DIST_NAME) or []
            runtime_requirements = [req for req in requirements if "extra ==" not in req]
            normalized_requirements = [req.replace(" ", "") for req in runtime_requirements]
            assert normalized_requirements == expected_runtime_requires

            for name in required_public_names:
                assert hasattr(gmp, name), f"missing root export: {name}"
                assert name in gmp.__all__, f"missing __all__ entry: {name}"

            package_root = resources.files(PACKAGE_NAME)
            py_typed = package_root.joinpath("py.typed")
            schema_resource = package_root.joinpath("schemas", "envelope.schema.json")
            assert py_typed.is_file()
            assert schema_resource.is_file()
            assert json.loads(schema_resource.read_text(encoding="utf-8")) == gmp.get_envelope_schema()

            files = metadata.files(DIST_NAME) or []
            file_names = {path.as_posix() for path in files}
            require_member(file_names, f"{PACKAGE_NAME}/__init__.py")
            require_member(file_names, f"{PACKAGE_NAME}/py.typed")
            require_member(file_names, f"{PACKAGE_NAME}/schemas/envelope.schema.json")
            assert_no_excluded_files(
                file_names,
                excluded_prefixes=excluded_prefixes,
                excluded_names=excluded_names,
                excluded_suffixes=excluded_suffixes,
            )

            replay_path = Path.cwd() / "fixture.raw.json"
            stage_dir = Path.cwd() / "stage"
            bundle_dir = Path.cwd() / "bundles"
            replay_path.write_text(json.dumps(raw_payload()), encoding="utf-8")

            env = gmp.parse_url(
                KENYALAW_URL,
                config=GazetteConfig(
                    runtime={
                        "replay_raw_json_path": replay_path,
                        "output_dir": stage_dir,
                    }
                ),
            )
            assert env.source.run_name == "gazette_2026-04-17_68"
            assert env.mistral.raw_json_path == str(replay_path)
            assert env.mistral.request_options["replay"] is True
            assert env.stats.page_count == 1
            assert env.stats.notice_count == 1
            assert env.stats.table_count == 1
            assert env.notices[0].notice_no == "5969"
            assert env.document_confidence.n_notices == 1
            assert env.layout_info.available is True
            assert not env.warnings

            written = gmp.write_envelope(env, bundle_dir, Bundles(schema=True))
            expected_keys = {
                "envelope",
                "source_metadata",
                "raw_mistral_json",
                "joined_markdown",
                "schema",
            }
            assert set(written) == expected_keys
            validated = gmp.validate_envelope_json(written["envelope"])
            assert validated.source.run_name == env.source.run_name
            assert written["schema"].read_bytes() == schema_resource.read_bytes()

        def raw_payload() -> dict[str, object]:
            return {
                "id": "doc_f12_install_smoke",
                "model": "mistral-ocr-latest",
                "pages": [
                    {
                        "index": 0,
                        "markdown": (
                            "## GAZETTE NOTICE NO. 5969\n\n"
                            "THE LAND REGISTRATION ACT\n\n"
                            "IN EXERCISE of the powers conferred by law, the Registrar gives notice.\n\n"
                            "| Parcel | Owner |\n"
                            "| --- | --- |\n"
                            "| Kajiado/1 | Jane Doe |\n\n"
                            "Dated the 17th April, 2026.\n\n"
                            "REGISTRAR,\n"
                            "Lands Registry."
                        ),
                        "dimensions": {"width": 719, "height": 1018},
                        "images": [{"bbox": [10, 20, 30, 40]}],
                    }
                ],
            }

        def require_member(names: set[str], member: str) -> None:
            if member not in names:
                raise AssertionError(f"installed distribution is missing {member}")

        def assert_no_excluded_files(
            names: set[str],
            *,
            excluded_prefixes: tuple[str, ...],
            excluded_names: set[str],
            excluded_suffixes: tuple[str, ...],
        ) -> None:
            for name in names:
                normalized = name.replace("\\", "/")
                basename = normalized.rsplit("/", 1)[-1]
                if normalized.startswith(excluded_prefixes):
                    raise AssertionError(f"unexpected runtime distribution file: {normalized}")
                if basename in excluded_names:
                    raise AssertionError(f"unexpected runtime distribution file: {normalized}")
                if normalized.endswith(excluded_suffixes):
                    raise AssertionError(f"unexpected runtime distribution file: {normalized}")

        if __name__ == "__main__":
            main()
        '''
    )


def assert_no_excluded_distribution_files(names: Iterable[str], *, source: str) -> None:
    for name in names:
        normalized = name.replace("\\", "/")
        basename = normalized.rsplit("/", 1)[-1]
        if normalized.startswith(EXCLUDED_DISTRIBUTION_PREFIXES):
            raise AssertionError(f"{source} unexpectedly contains {normalized}")
        if basename in EXCLUDED_DISTRIBUTION_NAMES:
            raise AssertionError(f"{source} unexpectedly contains {normalized}")
        if normalized.endswith(EXCLUDED_DISTRIBUTION_SUFFIXES):
            raise AssertionError(f"{source} unexpectedly contains {normalized}")


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> None:
    display = " ".join(command)
    print(f"+ {display}")
    subprocess.run(command, cwd=cwd, env=dict(env) if env is not None else None, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
