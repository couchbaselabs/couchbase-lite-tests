import os
import shutil
import zipfile
from pathlib import Path

import paramiko
from tqdm import tqdm


def sftp_progress_bar(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str):
    file_size = os.path.getsize(local_path)
    with tqdm(total=file_size, unit="B", unit_scale=True, desc=local_path.name) as bar:

        def callback(transferred, total):
            bar.update(transferred - bar.n)

        sftp.put(local_path, remote_path, callback=callback)


def zip_directory(input: Path, output: Path) -> None:
    if not input.exists():
        raise RuntimeError(f"Publish directory {input} does not exist (was it built?)")

    print("Zipping...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(input):
            for file in files:
                file_path = Path(root) / file
                print(" " * shutil.get_terminal_size().columns, end="\r")
                print(f"\t{file_path.relative_to(input)}", end="\r")
                zipf.write(file_path, file_path.relative_to(input))

    print(" " * shutil.get_terminal_size().columns, end="\r")
    print("Done")
