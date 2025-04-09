#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module sets up Couchbase Sync Gateway (SGW) on AWS EC2 instances. It includes functions for downloading SGW packages,
executing remote commands, setting up individual nodes, and configuring the SGW topology.

Classes:
    SgwDownloadInfo: A class to parse and store Sync Gateway download information.

Functions:
    lookup_sgw_build(version: str) -> int:
        Look up the build number for a given Sync Gateway version.

    download_sgw_package(download_info: SgwDownloadInfo) -> None:
        Download the Sync Gateway package if it is not a release version.

    setup_config(server_hostname: str) -> None:
        Write the server hostname to the bootstrap configuration file.

    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    setup_server(hostname: str, pkey: Optional[paramiko.Ed25519Key], sgw_info: SgwDownloadInfo) -> None:
        Set up a Sync Gateway server on an EC2 instance.

    setup_topology(pkey: Optional[paramiko.Ed25519Key], sgw_info: SgwDownloadInfo, topology: TopologyConfig) -> None:
        Set up the Sync Gateway topology on EC2 instances.

    main(download_url: str, topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Main function to set up the Sync Gateway topology.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Final, Optional, cast

import paramiko
import requests
from termcolor import colored
from tqdm import tqdm

from environment.aws.common.io import sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


class SgwDownloadInfo:
    """
    A class to parse and store Sync Gateway download information.

    Attributes:
        is_release (bool): Whether the download is a release version.
        local_filename (str): The local filename of the downloaded package.
        version (str): The version of Sync Gateway.
        build_no (int): The build number of Sync Gateway.
        url (str): The download URL of Sync Gateway.
    """

    __is_release_key: Final[str] = "IsRelease"
    __build_no_key: Final[str] = "BuildNumber"

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

    def _init_release(self, version: str):
        self.__version = version
        self.__build_no = 0
        self.__local_filename = (
            f"couchbase-sync-gateway-enterprise_{self.__version}_x86_64.rpm"
        )
        self.__url = f"https://packages.couchbase.com/releases/couchbase-sync-gateway/{self.__version}/{self.__local_filename}"

    def _init_internal(self, version: str, build_no: int):
        self.__version = version
        self.__build_no = build_no
        self.__local_filename = f"couchbase-sync-gateway-enterprise_{self.__version}-{self.__build_no}_x86_64.rpm"
        self.__url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/{self.__version}/{self.__build_no}/{self.__local_filename}"

    def __init__(self, version: str):
        if "-" in version:
            version_parts = version.split("-")
            self._init_internal(version_parts[0], int(version_parts[1]))
            return

        url = f"http://proget.build.couchbase.com:8080/api/get_version?product=sync_gateway&version={version}"
        r = requests.get(url)
        r.raise_for_status()
        version_info = cast(Dict, r.json())
        if self.__is_release_key not in version_info:
            json.dump(version_info, sys.stdout)
            raise ValueError("Invalid version information received from server.")

        if cast(bool, version_info[self.__is_release_key]):
            self._init_release(version)
        else:
            if self.__build_no_key not in version_info:
                json.dump(version_info, sys.stdout)
                raise ValueError("Invalid version information received from server.")
            self._init_internal(version, cast(int, version_info[self.__build_no_key]))


def lookup_sgw_build(version: str) -> int:
    """
    Look up the build number for a given Sync Gateway version.

    Args:
        version (str): The version of Sync Gateway.

    Returns:
        int: The build number of the specified version.

    Raises:
        requests.RequestException: If the request to the build server fails.
    """
    url = f"http://proget.build.couchbase.com:8080/api/get_version?product=sync_gateway&version={version}"
    r = requests.get(url)
    r.raise_for_status()
    return cast(int, r.json()["BuildNumber"])


def download_sgw_package(download_info: SgwDownloadInfo) -> None:
    """
    Download the Sync Gateway package if it is not a release version.

    Args:
        download_info (SgwDownloadInfo): The download information for Sync Gateway.

    Raises:
        requests.RequestException: If the request to download the package fails.
    """
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


def setup_config(server_hostname: str) -> None:
    """
    Write the server hostname to the bootstrap configuration file.

    Args:
        server_hostname (str): The hostname of the Couchbase Server.
    """
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


def remote_exec(
    ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True
) -> None:
    """
    Execute a remote command via SSH with a description and optional error handling.

    Args:
        ssh (paramiko.SSHClient): The SSH client.
        command (str): The command to execute.
        desc (str): A description of the command.
        fail_on_error (bool): Whether to raise an exception if the command fails.

    Raises:
        Exception: If the command fails and fail_on_error is True.
    """
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
) -> None:
    """
    Set up a Sync Gateway server on an EC2 instance.

    Args:
        hostname (str): The hostname or IP address of the EC2 instance.
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        sgw_info (SgwDownloadInfo): The download information for Sync Gateway.
    """
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
    topology: TopologyConfig,
) -> None:
    """
    Set up the Sync Gateway topology on EC2 instances.

    Args:
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        sgw_info (SgwDownloadInfo): The download information for Sync Gateway.
        topology (TopologyConfig): The topology configuration.
    """
    i = 0
    for sgw in topology.sync_gateways:
        sgw_info = SgwDownloadInfo(sgw.version)
        download_sgw_package(sgw_info)
        setup_config(sgw.cluster_hostname)
        setup_server(sgw.hostname, pkey, sgw_info)
        i += 1


def main(topology: TopologyConfig, private_key: Optional[str] = None) -> None:
    """
    Main function to set up the Sync Gateway topology.

    Args:
        topology (TopologyConfig): The topology configuration.
        private_key (Optional[str]): The path to the private key for SSH access.
    """
    if len(topology.sync_gateways) == 0:
        return

    pkey = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )

    setup_topology(pkey, topology)
