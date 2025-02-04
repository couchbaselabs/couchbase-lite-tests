import asyncio
from typing import Dict, List, Optional, Any
import asyncssh
import logging
import signal
import subprocess
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
            result = await self.ssh_client.run("pgrep -f /opt/couchbase-edge-server/bin/couchbase-edge-server", check=True)
            pid = result.stdout.strip()
            if pid:
                await self.ssh_client.run(f"kill {pid} && rm /tmp/edge_server.pid", check=True)
                return True
        except Exception as e:
            return False

    async def start_edge_server(self, config_file: str) -> bool:
        try:
            command=f"nohup /opt/couchbase-edge-server/bin/couchbase-edge-server --verbose {config_file} > /tmp/edge_server.log 2>&1 & echo $! > /tmp/edge_server.pid"
            await self.ssh_client.run(command, check=True)
            if await self.is_edge_server_running():
                return True
            return False
        except Exception as e:
            return False

    async def is_edge_server_running(self) -> bool:
        try:
            result = await self.ssh_client.run("pgrep -F /tmp/edge_server.pid", check=True)
            return bool(result.stdout.strip())
        except Exception:
            return False

    async def move_file(self,local_path,dest_path)->bool:
        try:
            await self.ssh_client.run(f"rm -r {dest_path}")
            subprocess.run(
                ["sshpass", "-p", "couchbase", "scp", local_path, f"root@{self._host}:{dest_path}"],check=True)
            await self.ssh_client.run(f"sudo chmod 644 {dest_path}")
            await self.ssh_client.run( f"sudo chown -R couchbase:couchbase {dest_path}")
            return True
        except Exception as e:
            return False
    async def add_user(self,name,password, role):
        command=f"/opt/couchbase-edge-server/bin/couchbase-edge-server --add-user /opt/couchbase-edge-server/users/users.json {name} --create --role {role} --password {password}"
        await self.ssh_client.run(command, check=True)

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

