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
import zipfile
from pathlib import Path

import paramiko
from requests import Response
from tqdm import tqdm


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

    print("Zipping...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(input):
            for file in tqdm(files, desc="Zipping"):
                file_path = Path(root) / file
                zipf.write(file_path, file_path.relative_to(input))

    print("Done")


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
            zipf.extract(member, output)
            extracted_path = output / member.filename

            # Preserve file permissions
            perm = member.external_attr >> 16
            if perm:
                extracted_path.chmod(perm)

    print("Done")
