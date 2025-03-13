#!/usr/bin/env python3

import json
import os
from pathlib import Path
from typing import Dict, Optional, cast

import paramiko
import requests
from environment.aws.common.output import header
from termcolor import colored
from environment.aws.topology_setup.setup_topology import TopologyConfig
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
    if download_info.is_release:
        return

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


def setup_config(server_hostname: str):
    header(f"Writing {server_hostname} to bootstrap.json as CBS IP")
    with open(SCRIPT_DIR / "config" / "bootstrap.json", "r") as fin:
        with open(SCRIPT_DIR / "bootstrap.json", "w") as fout:
            config_content = cast(Dict, json.load(fin))
            config_content["bootstrap"]["server"] = f"couchbases://{server_hostname}"
            json.dump(config_content, fout, indent=4)

    with open(SCRIPT_DIR / "start-sgw.sh.in", "r") as file:
        start_sgw_content = file.read()

    start_sgw_content = start_sgw_content.replace("{{server-ip}}", server_hostname)

    with open(SCRIPT_DIR / "start-sgw.sh", "w", newline="\n") as file:
        file.write(start_sgw_content)


def sftp_progress_bar(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str):
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


def setup_server(
    hostname: str, pkey: Optional[paramiko.Ed25519Key], sgw_info: SgwDownloadInfo
):
    if sgw_info.is_release:
        print(f"Setting up server {hostname} with SGW {sgw_info.version}")
    else:
        print(
            f"Setting up server {hostname} with SGW {sgw_info.version}-{sgw_info.build_no}"
        )

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username="ec2-user", pkey=pkey)

    global current_ssh
    current_ssh = hostname
    sftp = ssh.open_sftp()
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    remote_exec(ssh, "bash /tmp/configure-system.sh", "Setting up instance")

    if sgw_info.is_release:
        remote_exec(
            ssh,
            f"wget {sgw_info.url} -nc -O /tmp/{sgw_info.local_filename}",
            "Downloading Sync Gateway",
            fail_on_error=False,
        )
    else:
        sftp_progress_bar(
            sftp,
            SCRIPT_DIR / sgw_info.local_filename,
            f"/tmp/{sgw_info.local_filename}",
        )

    sftp_progress_bar(sftp, SCRIPT_DIR / "start-sgw.sh", "/home/ec2-user/start-sgw.sh")
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


def setup_topology(
    pkey: Optional[paramiko.Ed25519Key],
    sgw_info: SgwDownloadInfo,
    topology: TopologyConfig,
):
    if len(topology.sync_gateways) == 0:
        return

    i = 0
    for sgw in topology.sync_gateways:
        setup_config(sgw.cluster_hostname)
        setup_server(sgw.hostname, pkey, sgw_info)
        i += 1


def main(
    download_url: str, topology: TopologyConfig, private_key: Optional[str] = None
):
    sgw_info = SgwDownloadInfo(download_url)
    download_sgw_package(sgw_info)
    pkey = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )

    setup_topology(pkey, sgw_info, topology)
