#!/usr/bin/env python3

import os
from pathlib import Path
from typing import Optional

import paramiko
from environment.aws.common.output import header
from termcolor import colored
from environment.aws.topology_setup.setup_topology import TopologyConfig
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""


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

    _, stdout, stderr = ssh.exec_command(command)
    for line in iter(stdout.readline, ""):
        print(colored(f"[{current_ssh}] {line}", "light_grey"), end="")

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    print()


def setup_node(
    hostname: str,
    pkey: Optional[paramiko.Ed25519Key],
    version: str,
    cluster: Optional[str] = None,
):
    couchbase_filename = f"couchbase-server-enterprise-{version}-linux.x86_64.rpm"
    couchbase_url = (
        f"http://packages.couchbase.com/releases/{version}/{couchbase_filename}"
    )

    header(f"Setting up server {hostname} with version {version}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(hostname, username="ec2-user", pkey=pkey)

    sftp = ssh.open_sftp()
    sftp_progress_bar(sftp, SCRIPT_DIR / "configure-node.sh", "/tmp/configure-node.sh")
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh"
    )
    sftp_progress_bar(
        sftp, SCRIPT_DIR / "disable-thp.service", "/tmp/disable-thp.service"
    )
    sftp.close()

    global current_ssh
    current_ssh = hostname

    remote_exec(ssh, "sudo bash /tmp/configure-system.sh", "Setting up machine")
    remote_exec(
        ssh,
        f"wget -nc -O /tmp/{couchbase_filename} {couchbase_url} 2>&1",
        f"Downloading Couchbase Server {version}",
        fail_on_error=False,
    )
    remote_exec(
        ssh,
        "sudo rpm -e couchbase-server",
        "Uninstalling Couchbase Server",
        fail_on_error=False,
    )
    remote_exec(
        ssh,
        f"sudo rpm -i /tmp/{couchbase_filename}",
        f"Installing Couchbase Server {version}",
    )
    remote_exec(
        ssh, "sudo systemctl start couchbase-server", "Starting Couchbase Server"
    )

    config_command = "bash /tmp/configure-node.sh"
    if cluster is not None:
        config_command += f" {cluster}"
    remote_exec(ssh, config_command, "Setting up node")

    ssh.close()


def setup_topology(
    pkey: Optional[paramiko.Ed25519Key], version: str, topology: TopologyConfig
):
    if len(topology.clusters) == 0:
        return

    for cluster_config in topology.clusters:
        setup_node(cluster_config.public_hostnames[0], pkey, version)
        for server in cluster_config.public_hostnames[1:]:
            setup_node(server, pkey, version, cluster_config.public_hostnames[0])


def main(version: str, topology: TopologyConfig, private_key: Optional[str] = None):
    pkey = (
        paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
    )

    setup_topology(pkey, version, topology)
