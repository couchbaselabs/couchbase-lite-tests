import asyncio
from typing import Dict, List, Optional, Any
import asyncssh
import logging
import signal

from cbltest.version import VERSION
from opentelemetry.trace import get_tracer

_remote_shell_tracer = get_tracer("remote_shell", VERSION)

class RemoteShellConnection:
    def __init__(self, host: str, port: int = 59840, username: str = "root", password: str = "couchbase"):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._ssh_client: Optional[asyncssh.SSHClientConnection] = None

    async def connect(self):
        with _remote_shell_tracer.start_as_current_span("Connecting to remote shell" ,attributes={"ip": self._host}):

            self._ssh_client = await asyncssh.connect(
                self._host,
                username=self._username,
                password=self._password,
                known_hosts=None
            )



    @property
    def ssh_client(self):
        return self._ssh_client

    async def kill_edge_server(self) -> bool:
        try:
            command = f"lsof -i:{self._port}"
            result = await self.ssh_client.run(command, check=True)
            output = result.stdout.strip()

            if not output:
                return False

            # Parse the output to extract PIDs
            lines = output.split("\n")
            pids = set()
            for line in lines[1:]:  # Skip the header line
                parts = line.split()
                if len(parts) > 1:
                    pids.add(parts[1])  # PID is in the second column

            for pid in pids:
                kill_command = f"kill -{signal.SIGKILL} {pid}"
                await self.ssh_client.run(kill_command, check=True)

            return True

        except Exception as e:
            return False

    async def start_edge_server(self, secure: bool, config_file: str, certfile: str, keyfile: str) -> bool:
        try:
            if secure:
                start_command = (
                    f"./couchbase-lite-edgeserver --verbose --create-cert CN=localhost "
                    f"--cert {certfile} --key {keyfile} --config {config_file}"
                )
            else:
                start_command = (
                    f"./couchbase-lite-edgeserver --verbose --create-cert CN=localhost "
                    f"--config {config_file}"
                )

            await self.ssh_client.run(start_command, check=True)
            return True
        except Exception as e:
            return False

    async def run_command(self, curl_command: str):
        try:
            result = await self.ssh_client.run(curl_command, check=True)
            response = result.stdout.strip()
            return response
        except Exception as e:
            return e
    async def close(self):
        if self._ssh_client:
            self._ssh_client.close()
            await self._ssh_client.wait_closed()
            self._ssh_client = None
