#!/usr/bin/env python3

from typing import List, Optional
from tqdm import tqdm
from pathlib import Path
from termcolor import colored
from common.output import header
import paramiko
import argparse
import os

SCRIPT_DIR = Path(__file__).resolve().parent
current_ssh = ""
    
def sftp_progress_bar(sftp: paramiko.SFTP, local_path: Path, remote_path: str):
    file_size = os.path.getsize(local_path)
    with tqdm(total=file_size, unit='B', unit_scale=True, desc=local_path.name) as bar:
        def callback(transferred, total):
            bar.update(transferred - bar.n)
        sftp.put(local_path, remote_path, callback=callback)

def remote_exec(ssh: paramiko.SSHClient, command: str, desc: str):
    header(desc)
    
    _, stdout, stderr = ssh.exec_command(command)
    for line in iter(stdout.readline, ""):
        print(colored(f"[{current_ssh}] {line}", "light_grey"), end="")

    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")
    
    header('Done!')
    print()

def main(hostnames: List[str], version: str, private_key: Optional[str] = None):
    couchbase_filename = f"couchbase-server-enterprise-{version}-linux.x86_64.rpm"
    couchbase_url = f"http://packages.couchbase.com/releases/{version}/{couchbase_filename}"
    for hostname in hostnames:
        header(f"Setting up server {hostname} with version {version}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey: paramiko.Ed25519Key = paramiko.Ed25519Key.from_private_key_file(private_key) if private_key else None
        ssh.connect(hostname, username="ec2-user", pkey=pkey)

        sftp = ssh.open_sftp()
        sftp_progress_bar(sftp, SCRIPT_DIR / "configure-node.sh", "/tmp/configure-node.sh")
        sftp_progress_bar(sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh")
        sftp_progress_bar(sftp, SCRIPT_DIR / "disable-thp.service", "/tmp/disable-thp.service")
        sftp.close()

        global current_ssh
        current_ssh = hostname
        remote_exec(ssh, "sudo bash /tmp/configure-system.sh", "Setting up machine")
        remote_exec(ssh, f"wget -O /tmp/{couchbase_filename} {couchbase_url} 2>&1", f"Downloading Couchbase Server {version}")
        remote_exec(ssh, f"sudo rpm -i /tmp/{couchbase_filename}", f"Installing Couchbase Server {version}")
        remote_exec(ssh, "sudo systemctl start couchbase-server", "Starting Couchbase Server")
        remote_exec(ssh, "bash /tmp/configure-node.sh", "Setting up node")

        ssh.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a script over an SSH connection.")
    parser.add_argument("hostnames", nargs="+", help="The hostname or IP address of the server.")
    parser.add_argument("--version", default="7.6.4", help="The version of Couchbase Server to install.")
    parser.add_argument("--private-key", help="The private key to use for the SSH connection (if not default)")
    args = parser.parse_args()

    main(args.hostnames, args.version, args.private_key)