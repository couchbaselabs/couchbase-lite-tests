import json
import os
from pathlib import Path
import subprocess
import paramiko
import psutil
from typing import List, Optional

from tqdm import tqdm

from environment.aws.common.output import header
from .platform_bridge import PlatformBridge

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
        print(line, end="")

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        print(stderr.read().decode())
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    print()

class ExeBridge(PlatformBridge):
    def __init__(self, exe_path: str, extra_args: Optional[List[str]] = None):
        self.__exe_path = exe_path
        self.__extra_args = extra_args or []
        self.__exe_name = Path(self.__exe_path).name

    def validate(self, location: str) -> None:
        print("No validation needed for executables")

    def install(self, location: str) -> None:
        if location == "localhost":
            print("No action needed for installing executables locally")
            return

    def run(self, location: str) -> None:
        header(f"Running {self.__exe_path}")
        if len(self.__extra_args) > 0:
            print(f"Extra args: {json.dumps(self.__extra_args)}")
            print()

        args = [self.__exe_path]
        args.extend(self.__extra_args)
        process = subprocess.Popen(args, start_new_session=True)
        print(f"Started {self.__exe_name} with PID {process.pid}")

    def stop(self, location: str) -> None:
        header(f"Stopping test server '{self.__exe_name}'")
        for proc in psutil.process_iter():
            if proc.name() == self.__exe_name:
                proc.terminate()
                print(f"Stopped PID {proc.pid}")
                return
            
        print(f"Unable to find process to stop ({self.__exe_name})")
        
    def uninstall(self, location: str) -> None:
        print("No action needed for uninstalling executable")

    def get_ip(self, location):
        return location