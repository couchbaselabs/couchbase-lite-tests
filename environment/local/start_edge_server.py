#!/usr/bin/env python3
#
# Builds and runs Edge Server in a local Docker container, together with the Caddy and
# shell2http sidecars an AWS Edge Server host has, and writes a cbltest config naming it.
#
# Usage::
#
#   uv run environment/local/start_local.py --server rosmar --git-tag main
#   uv run environment/local/start_edge_server.py --version 1.1.1-3
#   cd tests/dev_e2e
#   uv run pytest --config ../../environment/local/edge_server/topology_config.json edge_server
#
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import click
import requests
from cryptography.x509 import ExtendedKeyUsageOID

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws.common.output import header
from environment.aws.common.x509_certificate import create_cert
from environment.aws.es_setup.setup_edge_servers import EsDownloadInfo, download_es_package, write_client_certs

DOCKER_DIR = SCRIPT_DIR / "edge_server"
AWS_DIR = SCRIPT_DIR.parent / "aws"
ES_SETUP_DIR = AWS_DIR / "es_setup"
TOPOLOGY_CONFIG_POINTER = SCRIPT_DIR / "topology_config"
EDGE_SERVER_TOPOLOGY_CONFIG = DOCKER_DIR / "topology_config.json"
DEFAULT_CONTAINER_NAME = "cbl-tests-edge-server"
IMAGE_NAME = "cbl-tests-edge-server"
# Edge Server, Caddy and shell2http, on the ports the test framework expects of an Edge Server host.
PORTS = (59840, 20000, 20001)
READY_TIMEOUT_SECONDS = 60


@click.command()
@click.option(
    "--version",
    help="Edge Server version, either a release (1.1.0) or an internal build (1.1.1-3). "
    "A version without a build number is looked up on proget, which needs the VPN. "
    "Required unless --stop is set.",
)
@click.option(
    "--container-name",
    default=DEFAULT_CONTAINER_NAME,
    show_default=True,
    help="Name of the Docker container. An existing container of this name is replaced.",
)
@click.option(
    "--base-config",
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="cbltest config to add the Edge Server to. Defaults to the one start_local.py last wrote, "
    "if any. Its Sync Gateway public ports are forwarded from the container to the host.",
)
@click.option("--stop", is_flag=True, help="Remove the container and exit.")
def main(version: str | None, container_name: str, base_config: pathlib.Path | None, stop: bool) -> None:
    if stop:
        remove_container(container_name)
        return

    if not version:
        raise click.UsageError("--version is required unless --stop is set.")

    base_config = base_config or previous_topology_config()
    config = json.loads(base_config.read_text()) if base_config else {}
    forward_ports = [sg.get("port", 4984) for sg in config.get("sync-gateways", [])]

    es_info = EsDownloadInfo(version, rpm_arch())
    rpm = download_es_package(es_info, include_release=True)

    with tempfile.TemporaryDirectory() as context:
        stage_build_context(pathlib.Path(context), rpm)
        header(f"Building {IMAGE_NAME} with {rpm.name}")
        _run(["docker", "build", "-t", IMAGE_NAME, context])

    remove_container(container_name)
    header(f"Starting {container_name}")
    _run(
        [
            "docker",
            "run",
            "-d",
            "--init",
            "--name",
            container_name,
            "--cap-add",
            "NET_ADMIN",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-e",
            f"HOST_FORWARD_PORTS={' '.join(str(p) for p in forward_ports)}",
            *(arg for port in PORTS for arg in ("-p", f"127.0.0.1:{port}:{port}")),
            IMAGE_NAME,
        ]
    )
    wait_for_edge_server(container_name)

    config["edge-servers"] = [{"hostname": "localhost"}]
    EDGE_SERVER_TOPOLOGY_CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    click.echo(f"Edge Server is up. Container logs: docker logs -f {container_name}")
    click.echo(f"Topology config for pytest written to {EDGE_SERVER_TOPOLOGY_CONFIG}")


def rpm_arch() -> str:
    """The RPM architecture matching this machine, so the container runs without emulation."""
    return "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"


def previous_topology_config() -> pathlib.Path | None:
    """The cbltest config start_local.py last wrote, if it is still there."""
    if not TOPOLOGY_CONFIG_POINTER.exists():
        return None
    path = pathlib.Path(TOPOLOGY_CONFIG_POINTER.read_text().strip())
    return path if path.exists() else None


def stage_build_context(context: pathlib.Path, rpm: pathlib.Path) -> None:
    """
    Copy in only what the image needs, rather than sending the whole repo as the build context.
    The certificates are minted the same way setup_edge_servers.py mints them for an AWS host.
    """
    for name in ("Dockerfile", "entrypoint.sh"):
        shutil.copy(DOCKER_DIR / name, context / name)
    shutil.copy(rpm, context / "edge-server.rpm")
    shutil.copy(ES_SETUP_DIR / "Caddyfile", context / "Caddyfile")
    shutil.copy(ES_SETUP_DIR / "config" / "config.json", context / "config.json")
    shutil.copytree(ES_SETUP_DIR / "dataset", context / "dataset")
    shutil.copytree(ES_SETUP_DIR / "shell2http", context / "shell2http")
    shutil.copy(AWS_DIR / "common" / "shell2http" / "with-timeout.sh", context / "shell2http")

    cert_dir = context / "cert"
    cert_dir.mkdir()
    ca = write_client_certs()
    cert = create_cert("localhost", ca, usages=[ExtendedKeyUsageOID.SERVER_AUTH])
    (cert_dir / "ca_cert.pem").write_bytes(ca.pem_bytes())
    (cert_dir / "es_cert.pem").write_bytes(cert.pem_bytes())
    (cert_dir / "es_key.pem").write_bytes(cert.private_pem_bytes())
    shutil.copy(AWS_DIR / "sgw_setup" / "cert" / "sg_cert.pem", cert_dir / "sg_cert.pem")


def wait_for_edge_server(container_name: str) -> None:
    """Wait until Edge Server and its shell2http sidecar both answer, or fail with the container log."""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            requests.get("http://localhost:59840/", timeout=1)
            requests.get("http://localhost:20001/", timeout=1)
            return
        except requests.RequestException:
            time.sleep(1)

    subprocess.run(["docker", "logs", container_name])
    raise click.ClickException(f"Edge Server did not answer within {READY_TIMEOUT_SECONDS}s")


def remove_container(container_name: str) -> None:
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
    EDGE_SERVER_TOPOLOGY_CONFIG.unlink(missing_ok=True)


def _run(cmd: list[str]) -> None:
    if subprocess.run(cmd).returncode != 0:
        raise click.ClickException(f"Command failed: {' '.join(cmd)}")


if __name__ == "__main__":
    main()
