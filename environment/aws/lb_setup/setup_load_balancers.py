"""
Sets up the load balancers on AWS EC2 instances: a Caddy container on each, with no upstreams.
Each test sets its own with `LoadBalancer.configure` from `cbltest.api.loadbalancer`.
"""

from pathlib import Path

from cbltest.api.loadbalancer import LoadBalancer

from environment.aws.common.docker import remote_exec, start_container
from environment.aws.common.io import get_ec2_hostname, sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.common.ssh import connect_ssh
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(__file__).resolve().parent
CONTAINER_NAME = "load-balancer"
IMAGE = "caddy:2.10.2"


def main(topology: TopologyConfig) -> None:
    """
    Set up the load balancers on AWS EC2 instances.

    Args:
        topology (TopologyConfig): The topology configuration that controls how many,
        if any, load balancers are needed.
    """
    if len(topology.load_balancers) == 0:
        return

    # An AWS load balancer listens on the default ports of a load balancer.
    ports = LoadBalancer(topology.load_balancers[0].hostname)
    docker_args = [
        "-e",
        f"CADDY_ADMIN=0.0.0.0:{ports.caddy_admin_port}",
        "-p",
        f"{ports.port}:{ports.port}",
        "-p",
        f"{ports.admin_port}:{ports.admin_port}",
        "-p",
        f"{ports.caddy_admin_port}:{ports.caddy_admin_port}",
    ]

    header("Setting up load balancers")
    for lb in topology.load_balancers:
        ec2_hostname = get_ec2_hostname(lb.hostname)
        with connect_ssh(ec2_hostname, topology.ssh_key) as ssh:
            sftp = ssh.open_sftp()
            sftp_progress_bar(sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh")
            sftp.close()
            remote_exec(ssh, "bash /tmp/configure-system.sh", fail_on_error=True)
            # An instance reused from before the move to Caddy still runs Traefik on the same ports.
            remote_exec(ssh, "docker rm -f traefik", fail_on_error=False)

        start_container(
            CONTAINER_NAME,
            IMAGE,
            ec2_hostname,
            topology.ssh_key,
            docker_args,
            container_args=["caddy", "run"],
            replace_existing=True,
        )
