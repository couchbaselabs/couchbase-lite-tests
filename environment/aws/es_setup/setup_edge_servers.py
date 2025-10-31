"""
This module sets up Couchbase Edge Server (ES) on AWS EC2 instances. It includes functions for downloading ES packages,
executing remote commands, setting up individual nodes, and configuring the ES topology.

Classes:
    EsDownloadInfo: A class to parse and store Edge Server download information.

Functions:
    lookup_es_build(version: str) -> int:
        Look up the build number for a given Edge Server version.

    download_es_package(download_info: EsDownloadInfo) -> None:
        Download the Edge Server package if it is not a release version.

    setup_config(server_hostname: str) -> None:
        Write the server hostname to the bootstrap configuration file.

    remote_exec(ssh: paramiko.SSHClient, command: str, desc: str, fail_on_error: bool = True) -> None:
        Execute a remote command via SSH with a description and optional error handling.

    setup_server(hostname: str, pkey: Optional[paramiko.Ed25519Key], es_info: EsDownloadInfo) -> None:
        Set up an Edge Server on an EC2 instance.

    setup_topology(pkey: Optional[paramiko.Ed25519Key], es_info: EsDownloadInfo, topology: TopologyConfig) -> None:
        Set up the Edge Server topology on EC2 instances.

    main(download_url: str, topology: TopologyConfig, private_key: Optional[str] = None) -> None:
        Main function to set up the Edge Server topology.
"""

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
from environment.aws.common.x509_certificate import create_self_signed_certificate
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


class EsDownloadInfo:
    """
    A class to parse and store Edge Server download information.

    Attributes:
        is_release (bool): Whether the download is a release version.
        local_filename (str): The local filename of the downloaded package.
        version (str): The version of Edge Server.
        build_no (int): The build number of Edge Server.
        url (str): The download URL of Edge Server.
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
        self.__local_filename = f"couchbase-edge-server-{self.__version}.x86_64.rpm"
        self.__url = f"https://packages.couchbase.com/releases/couchbase-edge-server/{self.__version}/{self.__local_filename}"

    def _init_internal(self, version: str, build_no: int):
        self.__version = version
        self.__build_no = build_no
        self.__local_filename = (
            f"couchbase-edge-server-{self.__version}-{self.__build_no}.x86_64.rpm"
        )
        self.__url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-edge-server/{self.__version}/{self.__build_no}/{self.__local_filename}"

    def __init__(self, version: str):
        if "-" in version:
            version_parts = version.split("-")
            self._init_internal(version_parts[0], int(version_parts[1]))
            return

        url = f"http://proget.build.couchbase.com:8080/api/get_version?product=couchbase-edge-server&version={version}"
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


def lookup_es_build(version: str) -> int:
    """
    Look up the build number for a given Edge Server version.

    Args:
        version (str): The version of Edge Server.

    Returns:
        int: The build number of the specified version.

    Raises:
        requests.RequestException: If the request to the build server fails.
    """
    url = f"http://proget.build.couchbase.com:8080/api/get_version?product=couchbase-edge-server&version={version}"
    r = requests.get(url)
    r.raise_for_status()
    return cast(int, r.json()["BuildNumber"])


def download_es_package(download_info: EsDownloadInfo) -> None:
    """
    Download the Edge Server package if it is not a release version.

    Args:
        download_info (EsDownloadInfo): The download information for Edge Server.

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
        click.secho(f"[{current_ssh}] {line}", fg=LIGHT_GRAY, nl=False)  # type: ignore

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()


def setup_server(
    hostname: str, pkey: paramiko.Ed25519Key | None, es_info: EsDownloadInfo
) -> None:
    """
    Set up an Edge Server on an EC2 instance.

    Args:
        hostname (str): The hostname or IP address of the EC2 instance.
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        es_info (EsDownloadInfo): The download information for Edge Server.
    """
    if es_info.is_release:
        click.echo(f"Setting up server {hostname} with ES {es_info.version}")
    else:
        click.echo(
            f"Setting up server {hostname} with ES {es_info.version}-{es_info.build_no}"
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

    if es_info.is_release:
        remote_exec(
            ssh,
            f"wget {es_info.url} -nc -O /tmp/{es_info.local_filename}",
            "Downloading Edge Server",
            fail_on_error=False,
        )
    else:
        sftp_progress_bar(
            sftp,
            SCRIPT_DIR / es_info.local_filename,
            f"/tmp/{es_info.local_filename}",
        )

    sftp_progress_bar(sftp, SCRIPT_DIR / "start-es.sh", "/home/ec2-user/start-es.sh")
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "es_config.json", "/home/ec2-user/config/es_config.json"
    )
    cert = create_self_signed_certificate(hostname)
    cert_pem = cert.pem_bytes()
    key_pem = cert.private_pem_bytes()
    with open("/tmp/es_key.pem", "wb") as f:
        f.write(key_pem)

    with open("/tmp/es_cert.pem", "wb") as f:
        f.write(cert_pem)

    sftp_progress_bar(sftp, Path("/tmp/es_cert.pem"), "/home/ec2-user/cert/es_cert.pem")
    sftp_progress_bar(sftp, Path("/tmp/es_key.pem"), "/home/ec2-user/cert/es_key.pem")

    Path("/tmp/es_key.pem").unlink()
    Path("/tmp/es_cert.pem").unlink()
    sftp.close()

    remote_exec(
        ssh,
        "sudo rpm -e couchbase-edge-server",
        "Uninstalling Couchbase Edge Server",
        fail_on_error=False,
    )

    remote_exec(
        ssh,
        f"sudo rpm -i /tmp/{es_info.local_filename}",
        "Installing Edge Server",
    )
    remote_exec(ssh, "bash /home/ec2-user/start-es.sh", "Starting Edge Server")

    ssh.close()


def setup_topology(
    pkey: paramiko.Ed25519Key | None,
    topology: TopologyConfig,
) -> None:
    """
    Set up the Sync Gateway topology on EC2 instances.

    Args:
        pkey (Optional[paramiko.Ed25519Key]): The private key for SSH access.
        es_info (EsDownloadInfo): The download information for Edge Server.
        topology (TopologyConfig): The topology configuration.
    """
    i = 0
    for es in topology.edge_servers:
        es_info = EsDownloadInfo(es.version)
        download_es_package(es_info)
        setup_server(es.hostname, pkey, es_info)
        i += 1


def main(topology: TopologyConfig, private_key: str | None = None) -> None:
    """
    Main function to set up the Sync Gateway topology.

    Args:
        topology (TopologyConfig): The topology configuration.
        private_key (Optional[str]): The path to the private key for SSH access.
    """
    if len(topology.edge_servers) == 0:
        return

    pkey = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )

    setup_topology(pkey, topology)
