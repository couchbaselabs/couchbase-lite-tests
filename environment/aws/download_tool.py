#!/usr/bin/env python3

import platform
import shutil
import stat
import sys
from enum import Enum
from pathlib import Path
from typing import Final

import click
import requests

SCRIPT_DIR: Final[Path] = Path(__file__).parent.resolve()

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[1]))
    from environment.aws.common.io import configure_terminal_encoding

    configure_terminal_encoding()

from environment.aws.common.io import (
    download_progress_bar,
    untar_directory,
    unzip_directory,
)
from environment.aws.common.output import header


class ToolName(Enum):
    BackupManager = "cbbackupmgr"
    BucketPool = "bucketpool"


_WINDOWS: Final[str] = "windows"
_MACOS: Final[str] = "macos"
_LINUX: Final[str] = "linux"

# The bucketpool release that empties Couchbase Server buckets between tests.
BUCKETPOOL_VERSION: Final[str] = "0.1.1"

TMP_LOCATION: Final[Path] = SCRIPT_DIR / ".tmp"
TOOLS_LOCATION: Final[Path] = SCRIPT_DIR.parents[1] / "tests" / ".tools"


# CLI entry point
@click.command()
@click.argument("name", type=click.Choice([a.value for a in ToolName]), required=True)
@click.argument("version", type=str, required=False)
def main(name: str, version: str | None) -> None:
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


def _get_go_arch() -> str:
    """The architecture name a Go release archive is published under."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"

    if machine in ("aarch64", "arm64"):
        return "arm64"

    raise RuntimeError(f"Unsupported architecture: {machine}")


def _get_ext(os: str) -> str:
    return "tar.gz" if os == _LINUX else "zip"


def _extract(location: Path) -> None:
    if location.suffix == ".zip":
        unzip_directory(location, location.parent)
    else:
        untar_directory(location, location.parent)


def tool_path(name: ToolName) -> Path:
    """The path the given tool is downloaded to, whether or not it exists yet."""
    binary = f"{name.value}.exe" if _get_os() == _WINDOWS else name.value
    return TOOLS_LOCATION / name.value / binary


# Entry for other scripts to call
def download_tool(name: ToolName, version: str | None = None) -> None:
    if name == ToolName.BackupManager:
        if version is None:
            raise RuntimeError(f"{name.value} needs an explicit version")

        os = _get_os()
        ext = _get_ext(os)
        url = (
            f"https://packages.couchbase.com/releases/{version}/"
            f"couchbase-server-dev-tools-{version}-{os}_{_get_arch(os)}.{ext}"
        )
    elif name == ToolName.BucketPool:
        version = version or BUCKETPOOL_VERSION
        os = _get_os()
        # The release archives use the Go platform names, so macos is darwin here.
        go_os = "darwin" if os == _MACOS else os
        ext = "zip" if os == _WINDOWS else "tar.gz"
        url = (
            f"https://github.com/couchbaselabs/bucketpool/releases/download/v{version}/"
            f"{name.value}_{version}_{go_os}_{_get_go_arch()}.{ext}"
        )
    else:
        raise RuntimeError(f"Unsupported tool: {name.value}")

    header(f"Downloading {name.value} v{version}")
    _install(name, version, url, ext)


def _install(name: ToolName, version: str, url: str, ext: str) -> None:
    """Downloads an archive, finds the tool inside it, and puts it in `tests/.tools`."""
    location = tool_path(name)
    version_location = location.parent / ".version"
    if version_location.exists() and location.exists() and version_location.read_text().strip() == version:
        click.secho("\t...already downloaded", fg="green")
        return

    version_location.unlink(missing_ok=True)
    location.unlink(missing_ok=True)
    location.parent.mkdir(parents=True, exist_ok=True)

    TMP_LOCATION.mkdir(parents=True, exist_ok=True)
    download = requests.get(url, stream=True)
    download.raise_for_status()
    tmp_file = TMP_LOCATION / f"download.{ext}"
    download_progress_bar(download, tmp_file)
    _extract(tmp_file)
    tmp_file.unlink()

    matches = [match for match in TMP_LOCATION.rglob(location.name) if match.is_file()]
    if not matches:
        raise RuntimeError(f"Could not find {location.name} in the archive downloaded from {url}")

    shutil.copy2(matches[0], location)
    shutil.rmtree(TMP_LOCATION)
    version_location.write_text(version)

    if _get_os() != _WINDOWS:
        mode = location.stat().st_mode
        location.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    click.secho("\t...done", fg="green")


if __name__ == "__main__":
    main()
