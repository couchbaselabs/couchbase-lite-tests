"""
A Caddy load balancer in Docker for the local environment.  It starts with no upstreams: each test
sets them with `LoadBalancer.configure` from `cbltest.api.loadbalancer`, which also documents the routing.
"""

import shutil
import subprocess
import time

import click
import requests
from cbltest.api.loadbalancer import LoadBalancer, caddy_config

CONTAINER_NAME = "cbl-tests-load-balancer"
IMAGE = "caddy:2.10.2"
# Host ports, chosen clear of the Sync Gateway port blocks that start at 4984.
PUBLIC_PORT = 4884
ENTRY = f"localhost:{PUBLIC_PORT}"
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


def start_load_balancer() -> str:
    """
    Start a fresh load balancer with no upstreams.

    :return: The `host:port` entry for the topology config's `load-balancers` list
    """
    stop_load_balancer()
    lb = LoadBalancer(ENTRY)
    # Inside the container, Caddy listens on the default ports of a load balancer.
    container = LoadBalancer("localhost")
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
            f"CADDY_ADMIN=0.0.0.0:{container.caddy_admin_port}",
            "-p",
            f"127.0.0.1:{lb.port}:{container.port}",
            "-p",
            f"127.0.0.1:{lb.admin_port}:{container.admin_port}",
            "-p",
            f"127.0.0.1:{lb.caddy_admin_port}:{container.caddy_admin_port}",
            IMAGE,
            "caddy",
            "run",
        ],
        check=True,
        capture_output=True,
    )
    _wait_for_admin_api(lb.caddy_admin_url)
    resp = requests.post(f"{lb.caddy_admin_url}/load", json=caddy_config([]), timeout=30)
    if resp.status_code != 200:
        raise click.ClickException(f"Caddy rejected the load balancer config ({resp.status_code}): {resp.text}")
    click.echo(f"Load balancer is up on {ENTRY}. Container logs: docker logs -f {CONTAINER_NAME}")
    return ENTRY
