#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, cast

import paramiko
import requests
from common.output import header
from termcolor import colored
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


class SgwDownloadInfo:
    @property
    def is_release(self) -> bool:
        return self.__build_no == 0

    @property
    def local_filename(self) -> str:
        return self.__local_filename

    @property
    def version(self) -> str:
        return self.__version

    @property
    def build_no(self) -> int:
        return self.__build_no

    @property
    def url(self) -> str:
        return self.__url

    def _parse_release_url(self, download_url: str):
        self.__local_filename = download_url.split("/")[-1]
        self.__version = download_url.split("/")[-2]
        self.__build_no = 0
        self.__url = download_url

    def _parse_internal_url(self, download_url: str):
        self.__local_filename = download_url.split("/")[-1]
        self.__version = download_url.split("/")[-3]
        self.__build_no = int(download_url.split("/")[-2])
        self.__url = download_url

    def __init__(self, download_url: str):
        if "latestbuilds" in download_url:
            self._parse_internal_url(download_url)
        else:
            self._parse_release_url(download_url)


def lookup_sgw_build(version: str) -> int:
    url = f"http://proget.build.couchbase.com:8080/api/get_version?product=sync_gateway&version={version}"
    r = requests.get(url)
    r.raise_for_status()
    return cast(int, r.json()["BuildNumber"])


def download_sgw_package(download_info: SgwDownloadInfo) -> None:
    local_path = SCRIPT_DIR / download_info.local_filename

    if not os.path.exists(local_path):
        header(f"Downloading {download_info.url} to {download_info.local_filename}")
        with requests.get(download_info.url, stream=True) as r:
            r.raise_for_status()
            with (
                open(local_path, "wb") as f,
                tqdm(
                    desc=download_info.local_filename,
                    total=int(r.headers.get("content-length", 0)),
                    unit="iB",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar,
            ):
                for chunk in r.iter_content(chunk_size=8192):
                    size = f.write(chunk)
                    bar.update(size)
    else:
        print(f"File {download_info.local_filename} already exists, skipping download.")


def setup_config():
    command = ["terraform", "output", "-json", "couchbase_instance_private_ips"]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    try:
        json_output = cast(List[str], json.loads(result.stdout))
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON output: {e}")

    if len(json_output) == 0:
        raise Exception("No server IPs found in Terraform output")

    header(f"Writing {json_output[0]} to bootstrap.json as CBS IP")
    with open(SCRIPT_DIR / "config" / "bootstrap.json", "r") as fin:
        with open(SCRIPT_DIR / "bootstrap.json", "w") as fout:
            config_content = cast(Dict, json.load(fin))
            config_content["bootstrap"]["server"] = f"couchbases://{json_output[0]}"
            json.dump(config_content, fout, indent=4)

    with open(SCRIPT_DIR / "start-sgw.sh.in", "r") as file:
        start_sgw_content = file.read()

    start_sgw_content = start_sgw_content.replace("{{server-ip}}", json_output[0])

    with open(SCRIPT_DIR / "start-sgw.sh", "w", newline="\n") as file:
        file.write(start_sgw_content)


def sftp_progress_bar(sftp: paramiko.SFTP, local_path: Path, remote_path: str):
    file_size = os.path.getsize(local_path)
    with tqdm(total=file_size, unit="B", unit_scale=True, desc=local_path.name) as bar:

        def callback(transferred, total):
            bar.update(transferred - bar.n)

        sftp.put(local_path, remote_path, callback=callback)


def remote_exec(
    ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True
):
    header(desc)

    _, stdout, stderr = ssh.exec_command(command, get_pty=True)
    for line in iter(stdout.readline, ""):
        print(colored(f"[{current_ssh}] {line}", "light_grey"), end="")

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    print()


def main(hostnames: List[str], download_url: str, private_key: Optional[str] = None):
    sgw_info = SgwDownloadInfo(download_url)
    download_sgw_package(sgw_info)
    setup_config()
    for hostname in hostnames:
        if sgw_info.is_release:
            print(f"Setting up server {hostname} with SGW {sgw_info.version}")
        else:
            print(
                f"Setting up server {hostname} with SGW {sgw_info.version}-{sgw_info.build_no}"
            )

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey: paramiko.Ed25519Key = (
            paramiko.Ed25519Key.from_private_key_file(private_key)
            if private_key
            else None
        )
        ssh.connect(hostname, username="ec2-user", pkey=pkey)

        global current_ssh
        current_ssh = hostname
        sftp = ssh.open_sftp()
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
        )
        remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")
        sftp_progress_bar(
            sftp,
            SCRIPT_DIR / sgw_info.local_filename,
            f"/tmp/{sgw_info.local_filename}",
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "start-sgw.sh", "/home/ec2-user/start-sgw.sh"
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "bootstrap.json", "/home/ec2-user/config/bootstrap.json"
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "cert" / "sg_cert.pem", "/home/ec2-user/cert/sg_cert.pem"
        )
        sftp_progress_bar(
            sftp, SCRIPT_DIR / "cert" / "sg_key.pem", "/home/ec2-user/cert/sg_key.pem"
        )
        sftp.close()

        remote_exec(
            ssh,
            "sudo rpm -e couchbase-sync-gateway",
            "Uninstalling Couchbase SGW",
            fail_on_error=False,
        )

        remote_exec(
            ssh,
            f"sudo rpm -i /tmp/{sgw_info.local_filename}",
            "Installing Sync Gateway",
        )
        remote_exec(ssh, "bash /home/ec2-user/start-sgw.sh", "Starting SGW")

        ssh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a script over an SSH connection.")
    parser.add_argument(
        "hostnames", nargs="+", help="The hostname or IP address of the server."
    )
    parser.add_argument(
        "--version", default="4.0.0", help="The version of Sync Gateway to install."
    )
    parser.add_argument(
        "--build",
        default=-1,
        type=int,
        help="The build number of Sync Gateway to install (latest good by default)",
    )
    parser.add_argument(
        "--private-key",
        help="The private key to use for the SSH connection (if not default)",
    )
    args = parser.parse_args()

    main(args.hostnames, args.version, args.build, args.private_key)
