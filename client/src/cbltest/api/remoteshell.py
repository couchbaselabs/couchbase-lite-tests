import asyncio
from typing import Dict, List, Optional, Any
import asyncssh
import logging
import signal
import subprocess
from cbltest.version import VERSION
from gevent.testing.travis import command
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
            command = "systemctl stop couchbase-edge-server"
            await self.ssh_client.run(command, check=True)
            return await self.is_edge_server_running()
        except Exception as e:
            return False

    async def start_edge_server(self) -> bool:
        try:
            command = " systemctl start couchbase-edge-server"
            await self.ssh_client.run(command, check=True)
            return True
        except Exception as e:
            return False

    async def reset_db_uuid(self, db_name: str) -> bool:
        try:
            command = f"/opt/couchbase-edge-server/bin/couchbase-edge-server --reset-uuid /opt/couchbase-edge-server/etc/{db_name}.cblite2"
            result=await self.ssh_client.run(command, check=True)
            if result.stderr.strip():
                return False
            return True
        except Exception as e:
            return False

    async def check_log(self, search_string: str, log_file: str) -> List[str]:
        try:
            command = f"grep '{search_string}' {log_file}"
            result = await self.ssh_client.run(command, check=True)
            matching_lines = result.stdout.strip().splitlines()
            return matching_lines
        except Exception as e:
            return []


    async def is_edge_server_running(self) -> bool:
        try:
            result = await self.ssh_client.run("systemctl status couchbase-edge-server", check=True)
            if "Stopped couchbase-edge-server.service" in result.stdout:
                return True
            return False
        except Exception:
            return False

    async def move_file(self,local_path,dest_path)->bool:
        try:
            await self.ssh_client.run(f"rm -r {dest_path}")
            subprocess.run(
                ["sshpass", "-p", "couchbase", "scp", local_path, f"root@{self._host}:{dest_path}"],check=True)
            await self.ssh_client.run(f" chmod 644 {dest_path}")
            await self.ssh_client.run( f" chown -R couchbase:couchbase {dest_path}")
            return True
        except Exception as e:
            return False
    async def add_user(self,name,password, role):
        try:
            command=f"/opt/couchbase-edge-server/bin/couchbase-edge-server --add-user /opt/couchbase-edge-server/users/users.json {name} --create --role {role} --password {password}"
            print(command)
            await self.ssh_client.run(command, check=True)
            return True
        except Exception as e:
            print(str(e))
            return False

    async def run_command(self, curl_command: str):
        try:
            result = await self.ssh_client.run(curl_command, check=True)
            response = result.stdout.strip()
            return response
        except Exception as e:
            return e
    async def reset_db(self,local_database_path=None):
        await self.ssh_client.run(
            "find /opt/couchbase-edge-server/database/ -type f -name '*.cblite2' -delete; "
            "find /opt/couchbase-edge-server/database/ -type d -name '*.cblite2' -exec rm -rf {} +"
        )
        if local_database_path is not None:
            await self.move_file(local_database_path,"/opt/couchbase-edge-server/database/db.cblite2.zip")
        cmd_check_unzip = "command -v unzip ||  apt-get update &&  apt-get install -y unzip"
        await self.ssh_client.run( cmd_check_unzip,check=True)
        await self.ssh_client.run( f"unzip -o /opt/couchbase-edge-server/database/db.cblite2.zip -d /opt/couchbase-edge-server/database",check=True)
        await self.ssh_client.run("chown -R couchbase:couchbase /opt/couchbase-edge-server/database")

    async def close(self):
        if self._ssh_client:
            self._ssh_client.close()
            await self._ssh_client.wait_closed()
            self._ssh_client = None

    async def kill_sgw(self):
        try:
            command=" systemctl stop sync_gateway"
            await self.ssh_client.run(command, check=True)
            return True
        except Exception as e:
            return False

    async def start_sgw(self, config_file: str) -> bool:
        try:
            command="systemctl restart sync_gateway"
            await self.ssh_client.run(command, check=True)
            return True
        except Exception as e:
            return False

