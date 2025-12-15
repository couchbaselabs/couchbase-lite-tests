#!/usr/bin/env python3

import platform
import shutil
import stat
import sys
from enum import Enum
from io import TextIOWrapper
from pathlib import Path
from typing import Final, cast

import click
import requests

SCRIPT_DIR: Final[Path] = Path(__file__).parent.resolve()

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.io import (
    download_progress_bar,
    untar_directory,
    unzip_directory,
)
from environment.aws.common.output import header


class ToolName(Enum):
    BackupManager = "cbbackupmgr"


_WINDOWS: Final[str] = "windows"
_MACOS: Final[str] = "macos"
_LINUX: Final[str] = "linux"

TMP_LOCATION: Final[Path] = SCRIPT_DIR / ".tmp"


# CLI entry point
@click.command()
@click.argument("name", type=click.Choice([a.value for a in ToolName]), required=True)
@click.argument("version", type=str, required=True)
def main(name: str, version: str):
    download_tool(ToolName(name), version)


def _get_os() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return _WINDOWS

    if system == "darwin":
        return _MACOS

    if system == "linux":
        return _LINUX

    raise RuntimeError(f"Unsupported OS: {system}")


def _get_arch(os: str) -> str:
    machine = platform.machine().lower()
    # Normalize common architecture aliases
    if machine in ("x86_64", "amd64"):
        return "amd64" if os == _WINDOWS else "x86_64"

    if machine in ("aarch64", "arm64"):
        return "aarch64" if os == _LINUX else "arm64"

    raise RuntimeError(f"Unsupported architecture: {machine}")


def _get_ext(os: str) -> str:
    return "tar.gz" if os == _LINUX else "zip"


def _extract(location: Path) -> None:
    if location.suffix == ".zip":
        unzip_directory(location, location.parent)
    else:
        untar_directory(location, location.parent)


# Entry for other scripts to call
def download_tool(name: ToolName, version: str):
    header(f"Downloading {name.value} v{version}")
    TMP_LOCATION.mkdir(parents=True, exist_ok=True)
    if name == ToolName.BackupManager:
        download_cbbackupmgr(version)
    else:
        raise RuntimeError(f"Unsupported tool: {name.value}")


def download_cbbackupmgr(version: str):
    os = _get_os()
    arch = _get_arch(os)
    ext = _get_ext(os)

    dest_dir = (
        SCRIPT_DIR.parent.parent / "tests" / ".tools" / ToolName.BackupManager.value
    )
    dest_name = (
        f"{ToolName.BackupManager.value}.exe"
        if os == _WINDOWS
        else ToolName.BackupManager.value
    )
    dest_version_name = ".version"
    version_location = dest_dir / dest_version_name
    if version_location.exists():
        existing_version = version_location.read_text().strip()
        if existing_version == version and (dest_dir / dest_name).exists():
            click.secho("\t...already downloaded", fg="green")
            return

    location = dest_dir / dest_name
    version_location.unlink(missing_ok=True)
    location.unlink(missing_ok=True)

    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://latestbuilds.service.couchbase.com/builds/releases/{version}/couchbase-server-admin-tools-{version}-{os}_{arch}.{ext}"
    download = requests.get(url, stream=True)
    download.raise_for_status()
    tmp_file = TMP_LOCATION / f"download.{ext}"
    download_progress_bar(download, tmp_file)
    _extract(tmp_file)
    tmp_file.unlink()
    version_location.write_text(version)

    # Find the cbbackupmgr binary in the extracted contents under TMP_LOCATION
    target_in_archive = "cbbackupmgr.exe" if os == _WINDOWS else "cbbackupmgr"
    matches = list(TMP_LOCATION.rglob(target_in_archive))
    if not matches:
        raise RuntimeError(
            f"Could not find {target_in_archive} in extracted archive {tmp_file}"
        )

    # Choose the first match
    src_path = next(match for match in matches if match.is_file())
    shutil.copy2(src_path, location)
    shutil.rmtree(TMP_LOCATION)

    # Ensure executable on non-Windows
    if os != _WINDOWS:
        try:
            mode = location.stat().st_mode
            location.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass
    click.secho("\t...done", fg="green")


if __name__ == "__main__":
    main()
