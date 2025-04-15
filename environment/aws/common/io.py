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
import tarfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

import click
import paramiko
from requests import Response
from tqdm import tqdm

LIGHT_GRAY = (128, 128, 128)


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


def zip_directory(input: Path, output: Path) -> None:
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

    click.echo("Zipping...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(input):
            for file in tqdm(files, desc="Zipping"):
                file_path = Path(root) / file
                zipf.write(file_path, file_path.relative_to(input))

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


@contextmanager
def pushd(new_dir: Path):
    prev_dir = Path.cwd()
    try:
        os.chdir(new_dir)
        yield
    finally:
        os.chdir(prev_dir)
