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

    setup_server(hostname: str, pkey: paramiko.Ed25519Key, sgw_info: SgwDownloadInfo) -> None:
        Set up a Sync Gateway server on an EC2 instance.

    main(download_url: str, topology: TopologyConfig) -> None:
        Main function to set up the Sync Gateway topology.
"""

import copy
import json
import os
import sys
from pathlib import Path
from typing import Final, cast

import click
import paramiko
import requests
from tqdm import tqdm

from environment.aws.common.io import LIGHT_GRAY, sftp_progress_bar
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
            f"couchbase-sync-gateway-enterprise_{self.__version}_aarch64.rpm"
        )
        self.__url = f"https://packages.couchbase.com/releases/couchbase-sync-gateway/{self.__version}/{self.__local_filename}"

    def _init_internal(self, version: str, build_no: int):
        self.__version = version
        self.__build_no = build_no
        self.__local_filename = f"couchbase-sync-gateway-enterprise_{self.__version}-{self.__build_no}_aarch64.rpm"
        self.__url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/{self.__version}/{self.__build_no}/{self.__local_filename}"

    def __init__(self, version: str):
        if "-" in version:
            version_parts = version.split("-")
            self._init_internal(version_parts[0], int(version_parts[1]))
            return

        url = f"http://proget.build.couchbase.com:8080/api/get_version?product=sync_gateway&version={version}"
        r = requests.get(url)
        r.raise_for_status()
        version_info = cast(dict, r.json())
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
        click.secho(
            f"File {download_info.local_filename} already exists, skipping download.",
            fg="yellow",
        )


def setup_config(server_hostname: str) -> None:
    """
    Write the server hostname to the bootstrap configuration files.

    Args:
        server_hostname (str): The hostname of the Couchbase Server.
    """
    header(f"Writing {server_hostname} to bootstrap configs as CBS IP")

    # Load base template
    with open(SCRIPT_DIR / "config" / "bootstrap.json") as fin:
        base_config = cast(dict, json.load(fin))

    # 1. Default bootstrap.json
    default_config = copy.deepcopy(base_config)
    default_config["bootstrap"]["server"] = f"couchbases://{server_hostname}"
    with open(SCRIPT_DIR / "bootstrap.json", "w") as fout:
        json.dump(default_config, fout, indent=4)

    # 2. bootstrap-alternate.json (with explicit port for alternate address testing)
    alternate_config = copy.deepcopy(base_config)
    alternate_config["bootstrap"]["server"] = f"couchbases://{server_hostname}:11207"
    with open(SCRIPT_DIR / "bootstrap-alternate.json", "w") as fout:
        json.dump(alternate_config, fout, indent=4)

    # 3. bootstrap-x509-cacert-only.json (with x509 CA cert for CBS testing)
    x509_config = copy.deepcopy(base_config)
    x509_config["bootstrap"]["server"] = f"couchbases://{server_hostname}"
    x509_config["bootstrap"]["server_tls_skip_verify"] = False
    x509_config["bootstrap"]["ca_cert_path"] = "/home/ec2-user/cert/cbs-ca-cert.pem"
    with open(SCRIPT_DIR / "bootstrap-x509-cacert-only.json", "w") as fout:
        json.dump(x509_config, fout, indent=4)

    # 4. bootstrap-cbs-alternate.json (with custom CBS ports for CBS testing)
    cbs_alternate_config = copy.deepcopy(base_config)
    cbs_alternate_config["bootstrap"]["server"] = (
        f"couchbases://{server_hostname}:11207"
    )
    with open(SCRIPT_DIR / "bootstrap-cbs-alternate.json", "w") as fout:
        json.dump(cbs_alternate_config, fout, indent=4)

    with open(SCRIPT_DIR / "start-sgw.sh.in") as file:
        start_sgw_content = file.read()

    start_sgw_content = "#!/bin/sh\n\n" + start_sgw_content.replace(
        "{{server-ip}}", server_hostname
    )

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
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def remote_exec_bg(ssh: paramiko.SSHClient, command: str, desc: str) -> None:
    """
    Execute a remote command in background via SSH.

    Args:
        ssh (paramiko.SSHClient): The SSH client.
        command (str): The command to execute.
        desc (str): A description of the command.
    """
    header(desc)
    ssh.exec_command(command, get_pty=False)
    header("Done!")
    click.echo()


def setup_server(
    hostname: str, pkey: paramiko.Ed25519Key, sgw_info: SgwDownloadInfo
) -> None:
    """
    Set up a Sync Gateway server on an EC2 instance.

    Args:
        hostname (str): The hostname or IP address of the EC2 instance.
        pkey (paramiko.Ed25519Key): The private key for SSH access.
        sgw_info (SgwDownloadInfo): The download information for Sync Gateway.
    """
    if sgw_info.is_release:
        click.echo(f"Setting up server {hostname} with SGW {sgw_info.version}")
    else:
        click.echo(
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
        try:
            existing_remote = sftp.stat(f"/tmp/{sgw_info.local_filename}")
        except OSError:
            existing_remote = None  # File doesn't exist on remote
        existing_local = os.stat(SCRIPT_DIR / sgw_info.local_filename)
        if existing_remote and existing_remote.st_size == existing_local.st_size:
            click.secho(
                f"File {sgw_info.local_filename} already exists on remote, skipping upload.",
                fg="green",
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
        sftp,
        SCRIPT_DIR / "bootstrap-alternate.json",
        "/home/ec2-user/config/bootstrap-alternate.json",
    )
    sftp_progress_bar(
        sftp,
        SCRIPT_DIR / "bootstrap-x509-cacert-only.json",
        "/home/ec2-user/config/bootstrap-x509-cacert-only.json",
    )
    sftp_progress_bar(
        sftp,
        SCRIPT_DIR / "bootstrap-cbs-alternate.json",
        "/home/ec2-user/config/bootstrap-cbs-alternate.json",
    )
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "cert" / "sg_cert.pem", "/home/ec2-user/cert/sg_cert.pem"
    )
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "cert" / "sg_key.pem", "/home/ec2-user/cert/sg_key.pem"
    )
    sftp_progress_bar(sftp, SCRIPT_DIR / "Caddyfile", "/home/ec2-user/Caddyfile")
    for file in (SCRIPT_DIR / "shell2http").iterdir():
        sftp_progress_bar(sftp, file, f"/home/ec2-user/shell2http/{file.name}")
    sftp.close()

    # Make shell2http scripts executable
    remote_exec(
        ssh,
        "chmod +x /home/ec2-user/shell2http/*.sh",
        "Making shell2http scripts executable",
    )

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

    remote_exec(ssh, "/home/ec2-user/caddy start", "Starting SGW log fileserver")
    remote_exec_bg(
        ssh,
        "bash /home/ec2-user/shell2http/start.sh",
        "Starting SGW management server",
    )
    remote_exec(ssh, "bash /home/ec2-user/start-sgw.sh", "Starting SGW")

    ssh.close()


def main(topology: TopologyConfig) -> None:
    """
    Set up the Sync Gateway topology on EC2 instances.

    Args:
        topology (TopologyConfig): The topology configuration.
    """
    if len(topology.sync_gateways) == 0:
        return

    i = 0
    for sgw in topology.sync_gateways:
        sgw_info = SgwDownloadInfo(sgw.version)
        download_sgw_package(sgw_info)
        setup_config(sgw.cluster_hostname)
        setup_server(sgw.hostname, topology.ssh_key, sgw_info)
        i += 1
