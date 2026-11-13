"""
A Caddy load balancer in Docker for the local environment.  It starts with no upstreams: each test
sets them with `LoadBalancer.configure` from `cbltest.api.loadbalancer`, which also documents the routing.
"""

import shutil
import subprocess
import time
from typing import Any

import click
import requests
from cbltest.api.loadbalancer import LoadBalancer, caddy_config
from cbltest.configparser import LoadBalancerInfo

CONTAINER_NAME = "cbl-tests-load-balancer"
IMAGE = "caddy:2.10.2"
# Clear of the Sync Gateway port blocks that start at 4984, and of the local Edge Server's 20000.
ENTRY: dict[str, Any] = {
    "hostname": "localhost",
    "port": 4884,
    "admin_port": 4885,
    "caddy_admin_port": 19900,
}
# Inside the container, localhost is the container itself, so Caddy reaches the host's Sync Gateway by this name.
SYNC_GATEWAY_INTERNAL_HOSTNAME = "host.docker.internal"
STARTUP_TIMEOUT_SECONDS = 30


def _wait_for_admin_api(admin_url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{admin_url}/config/", timeout=2).status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    logs = subprocess.run(["docker", "logs", CONTAINER_NAME], capture_output=True, text=True)
    raise click.ClickException(
        f"Caddy's admin API did not answer within {STARTUP_TIMEOUT_SECONDS}s:\n{logs.stdout}{logs.stderr}"
    )


def stop_load_balancer() -> bool:
    """Remove the load balancer container, returning whether one was there."""
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, text=True)
    return result.returncode == 0


def start_load_balancer() -> dict[str, Any]:
    """
    Start a fresh load balancer with no upstreams.

    :return: The entry for the topology config's `load-balancers` list
    """
    stop_load_balancer()
    info = LoadBalancerInfo(ENTRY)
    lb = LoadBalancer(info)
    # Caddy listens inside the container on the same ports the host publishes.
    ports = [f"127.0.0.1:{port}:{port}" for port in (info.port, info.admin_port, info.caddy_admin_port)]
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "--add-host",
            "host.docker.internal:host-gateway",
            "-e",
            f"CADDY_ADMIN=0.0.0.0:{info.caddy_admin_port}",
            *(arg for port in ports for arg in ("-p", port)),
            IMAGE,
            "caddy",
            "run",
        ],
        check=True,
        capture_output=True,
    )
    _wait_for_admin_api(lb.caddy_admin_url)
    resp = requests.post(
        f"{lb.caddy_admin_url}/load",
        data=caddy_config(info, []),
        headers={"Content-Type": "text/caddyfile"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise click.ClickException(f"Caddy rejected the load balancer config ({resp.status_code}): {resp.text}")
    click.echo(f"Load balancer is up on {lb.hostname}:{lb.port}. Container logs: docker logs -f {CONTAINER_NAME}")
    return ENTRY
