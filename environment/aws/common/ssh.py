"""
SSH connections to the EC2 instances Terraform creates.

Terraform reports an instance as running well before cloud-init has installed the key and
started sshd, so a connection made right after `terraform apply` loses a race it cannot see
-- and loses it again whenever an instance is replaced. Every connection here waits for the
instance to answer instead.
"""

import time

import click
import paramiko

CONNECT_TIMEOUT: int = 300
"""How long to keep trying an instance that is still booting, in seconds."""

_RETRY_INTERVAL: int = 5
"""Seconds between attempts.  A boot takes tens of seconds, so a tighter loop only adds noise."""

_SOCKET_TIMEOUT: int = 15
"""Seconds one attempt waits, so a silent host fails the attempt rather than the whole wait."""


def connect_ssh(
    hostname: str,
    pkey: paramiko.PKey | None = None,
    *,
    username: str = "ec2-user",
    password: str | None = None,
    timeout: int = CONNECT_TIMEOUT,
) -> paramiko.SSHClient:
    """
    Connect to a host, waiting for it to accept SSH if it is still booting.

    :param hostname: Host to connect to
    :param pkey: Private key to authenticate with, or None to use `password`
    :param username: User to connect as
    :param password: Password to authenticate with, for hosts that take one
    :param timeout: How long to keep trying, in seconds
    :return: A connected SSHClient, which the caller closes
    """
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    deadline = time.monotonic() + timeout
    waiting = False
    while True:
        try:
            ssh.connect(
                hostname,
                username=username,
                pkey=pkey,
                password=password,
                timeout=_SOCKET_TIMEOUT,
            )
            if waiting:
                click.echo(f"{hostname} is accepting SSH")
            return ssh
        # An authentication failure is not a boot in progress: the credentials are wrong,
        # and waiting does not make them right.  It subclasses SSHException, so it has to
        # be turned away before the retry below sees it.
        except paramiko.AuthenticationException:
            ssh.close()
            raise
        # No listener yet, a listener that hangs up, or sshd accepting the socket before it
        # can speak SSH -- all of them are what a booting instance looks like.
        except (paramiko.SSHException, OSError) as e:
            if time.monotonic() >= deadline:
                ssh.close()
                raise TimeoutError(f"{hostname} did not accept SSH within {timeout}s: {e}") from e

            if not waiting:
                click.echo(f"Waiting for {hostname} to accept SSH...")
                waiting = True
            time.sleep(_RETRY_INTERVAL)
