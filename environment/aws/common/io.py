"""
This module provides utility functions for I/O operations, including downloading files with a progress bar,
uploading files via SFTP with a progress bar, and zipping/unzipping directories.

Functions:
    download_progress_bar(response: Response, output_path: Path) -> None:
        Download a file with a progress bar.

    sftp_progress_bar(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
        Upload a file via SFTP with a progress bar.

    zip_directory(input: Path, output: Path) -> None:
        Zip the contents of a directory.

    unzip_directory(input: Path, output: Path) -> None:
        Unzip the contents of a zip file to a directory.
"""

import os
import sys
import tarfile
import time
import zipfile
from contextlib import contextmanager
from fnmatch import fnmatch
from pathlib import Path

import click
import paramiko
from paramiko import Channel, ChannelFile
from requests import Response
from tqdm import tqdm

LIGHT_GRAY = (128, 128, 128)


def write_chunk(channel: Channel) -> None:
    chunk = channel.recv(1024).decode(errors="ignore")
    if chunk:
        click.secho(chunk, fg=LIGHT_GRAY, nl=False)


def realtime_output(stdout: ChannelFile) -> None:
    channel = stdout.channel
    while True:
        if channel.recv_ready():
            write_chunk(channel)
        if channel.exit_status_ready():
            # drain remaining output
            while channel.recv_ready():
                write_chunk(channel)

            break

        time.sleep(0.1)


def download_progress_bar(response: Response, output_path: Path) -> None:
    """
    Download a file with a progress bar.

    Args:
        response (Response): The HTTP response object.
        output_path (Path): The path where the downloaded file will be saved.

    Raises:
        RuntimeError: If the response does not contain a content-length header.
    """
    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024

    with (
        open(output_path, "wb") as f,
        tqdm(total=total_size, unit="iB", unit_scale=True) as progress_bar,
    ):
        for data in response.iter_content(block_size):
            progress_bar.update(len(data))
            f.write(data)


def sftp_progress_bar(
    sftp: paramiko.SFTPClient, local_path: Path, remote_path: str
) -> None:
    """
    Upload a file via SFTP with a progress bar.

    Args:
        sftp (paramiko.SFTPClient): The SFTP client.
        local_path (Path): The path to the local file to be uploaded.
        remote_path (str): The remote path where the file will be uploaded.
    """
    file_size = os.path.getsize(local_path)
    with tqdm(total=file_size, unit="B", unit_scale=True, desc=local_path.name) as bar:

        def callback(transferred, total):
            bar.update(transferred - bar.n)

        sftp.put(local_path, remote_path, callback=callback)


def zip_directory(input: Path, output: Path, excludes: list[str] | None = None) -> None:
    """
    Zip the contents of a directory.

    Args:
        input (Path): The path to the directory to be zipped.
        output (Path): The path where the zip file will be saved.

    Raises:
        RuntimeError: If the input directory does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    excludes = excludes or []

    def is_excluded(rel_path: Path, is_dir: bool) -> bool:
        rel_posix = rel_path.as_posix()
        # For directories also test pattern with trailing slash variants
        for pat in excludes:
            # Expand simple directory name patterns (e.g. '__pycache__')
            if is_dir and not any(ch in pat for ch in "*?[]") and "/" not in pat:
                if rel_posix == pat:
                    return True
            # Direct match
            if fnmatch(rel_posix, pat):
                return True
            # Allow directory patterns written without trailing /** by user
            if is_dir and (
                fnmatch(rel_posix + "/", pat) or fnmatch(rel_posix + "/.", pat)
            ):
                return True
        return False

    click.echo("Zipping...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(input):
            root_path = Path(root)
            pruned_dirs = []
            for d in dirs:
                rel_dir = (root_path / d).relative_to(input)
                if is_excluded(rel_dir, is_dir=True):
                    continue
                pruned_dirs.append(d)
            dirs[:] = pruned_dirs

            for file in files:
                rel_file = (root_path / file).relative_to(input)
                if is_excluded(rel_file, is_dir=False):
                    continue
                file_path = root_path / file
                zipf.write(file_path, rel_file)

    click.echo("Done")


def unzip_directory(input: Path, output: Path) -> None:
    """
    Unzip the contents of a zip file to a directory.

    Args:
        input (Path): The path to the zip file to be unzipped.
        output (Path): The path where the contents will be extracted.

    Raises:
        RuntimeError: If the input zip file does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    with zipfile.ZipFile(input, "r") as zipf:
        for member in tqdm(zipf.infolist(), desc="Unzipping"):
            extracted_path = output / member.filename
            # Check if the member is a symlink
            is_symlink = (member.external_attr >> 16) & 0o120000 == 0o120000
            if is_symlink:
                # Read the symlink target from the ZIP file
                with zipf.open(member) as link_file:
                    target = link_file.read().decode("utf-8")

                # Create the symlink
                extracted_path.parent.mkdir(parents=True, exist_ok=True)
                extracted_path.symlink_to(target)
            else:
                # Extract regular files and directories
                zipf.extract(member, output)
                # Preserve file permissions
                perm = member.external_attr >> 16
                if perm:
                    extracted_path.chmod(perm)

    click.echo("Done")


def tar_directory(input: Path, output: Path) -> None:
    """
    Create a .tar.gz archive of the contents of a directory.

    Args:
        input (Path): The path to the directory to be archived.
        output (Path): The path where the .tar.gz file will be saved.

    Raises:
        RuntimeError: If the input directory does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    click.echo("Compressing")
    with tarfile.open(output, "w:gz") as tar:
        for root, _, files in os.walk(input):
            for file in tqdm(files, desc="Archiving"):
                file_path = Path(root) / file
                tar.add(file_path, arcname=file_path.relative_to(input))

    click.echo("Done")


def untar_directory(input: Path, output: Path) -> None:
    """
    Extract the contents of a .tar.gz archive to a directory.

    Args:
        input (Path): The path to the .tar.gz file to be extracted.
        output (Path): The path where the contents will be extracted.

    Raises:
        RuntimeError: If the input .tar.gz file does not exist.
    """
    if not input.exists():
        raise RuntimeError(f"{input} does not exist...")

    click.echo("Extracting")
    with tarfile.open(input, "r:gz") as tar:
        for member in tqdm(tar.getmembers(), desc="Extracting"):
            tar.extract(member, path=output)

            # Preserve file permissions
            extracted_path = output / member.name
            if member.mode and not member.islnk() and not member.issym():
                extracted_path.chmod(member.mode)

    click.echo("Done")


def get_ec2_hostname(hostname: str) -> str:
    """
    Convert an IP address to an EC2 hostname.

    Args:
        hostname (str): The IP address.

    Returns:
        str: The EC2 hostname.

    Raises:
        ValueError: If the hostname is not an IP address.
    """
    if hostname.startswith("ec2-"):
        return hostname

    components = hostname.split(".")
    if len(components) != 4:
        raise ValueError(f"Invalid hostname {hostname}")

    return f"ec2-{hostname.replace('.', '-')}.compute-1.amazonaws.com"


def configure_terminal_encoding() -> None:
    """
    Configure stdout and stderr to use UTF-8 encoding.

    This is useful when running scripts in environments with non-UTF-8
    terminal encoding (e.g., Windows cmd, certain Unix locales).

    Uses reconfigure() method if available (Python 3.7+ TextIOWrapper).
    """
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if callable(stdout_reconfigure):
        stdout_reconfigure(encoding="utf-8")
    if callable(stderr_reconfigure):
        stderr_reconfigure(encoding="utf-8")


@contextmanager
def pushd(new_dir: Path):
    prev_dir = Path.cwd()
    try:
        os.chdir(new_dir)
        yield
    finally:
        os.chdir(prev_dir)
