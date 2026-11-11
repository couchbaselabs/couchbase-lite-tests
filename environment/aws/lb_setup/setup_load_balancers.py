"""
Sets up the load balancers on AWS EC2 instances: a Caddy container on each, with no upstreams.
Each test sets its own with `LoadBalancer.configure` from `cbltest.api.loadbalancer`.
"""

from pathlib import Path

from cbltest.configparser import LoadBalancerInfo

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

    # The TDK config names only the hostname, so the client uses the default ports too.
    caddy_admin_port = LoadBalancerInfo.DEFAULT_CADDY_ADMIN_PORT
    docker_args = ["-e", f"CADDY_ADMIN=0.0.0.0:{caddy_admin_port}"]
    for port in (LoadBalancerInfo.DEFAULT_PORT, LoadBalancerInfo.DEFAULT_ADMIN_PORT, caddy_admin_port):
        docker_args += ["-p", f"{port}:{port}"]

    header("Setting up load balancers")
    for lb in topology.load_balancers:
        ec2_hostname = get_ec2_hostname(lb.hostname)
        with connect_ssh(ec2_hostname, topology.ssh_key) as ssh:
            sftp = ssh.open_sftp()
            sftp_progress_bar(sftp, SCRIPT_DIR / "configure-system.sh", "/tmp/configure-system.sh")
            sftp.close()
            remote_exec(ssh, "bash /tmp/configure-system.sh", fail_on_error=True)

        start_container(
            CONTAINER_NAME,
            IMAGE,
            ec2_hostname,
            topology.ssh_key,
            docker_args,
            container_args=["caddy", "run"],
            replace_existing=True,
        )
