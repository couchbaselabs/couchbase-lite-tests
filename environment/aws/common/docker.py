import click
import paramiko

from environment.aws.common.io import realtime_output
from environment.aws.common.output import header


def remote_exec(
    ssh: paramiko.SSHClient,
    command: str,
    fail_on_error: bool = True,
    capture_output: bool = False,
) -> str | None:
    _, stdout, stderr = ssh.exec_command(command, get_pty=True)

    if not capture_output:
        realtime_output(stdout)

    exit_status = stdout.channel.recv_exit_status()
    if fail_on_error and exit_status != 0:
        click.secho(stderr.read().decode(), fg="red")
        raise Exception(f"Command '{command}' failed with exit status {exit_status}")

    header("Done!")
    click.echo()
    return stdout.read().decode() if capture_output else None


def start_container(
    name: str,
    image_name: str,
    host: str,
    pkey: paramiko.Ed25519Key,
    docker_args: list[str] | None = None,
    container_args: list[str] | None = None,
    replace_existing: bool = False,
) -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="ec2-user", pkey=pkey)

    header(f"Starting {name} on {host}")
    container_check = remote_exec(
        ssh,
        f"docker ps -a --filter name={name} --format {{{{.Status}}}}",
        fail_on_error=True,
        capture_output=True,
    )

    if container_check and container_check.strip() != "":
        if container_check.startswith("Up"):
            if not replace_existing:
                click.echo(f"{name} already running, returning...")
                return

            click.echo(f"Stopping existing {name} container...")
            remote_exec(ssh, f"docker stop {name}", fail_on_error=True)

        if not replace_existing:
            click.echo(f"Restarting existing {name} container...")
            remote_exec(ssh, f"docker start {name}", fail_on_error=True)
            return

    click.echo(f"Starting new {name} container...")
    args = [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        name,
    ]

    if docker_args:
        args.extend(docker_args)

    args.append(image_name)

    if container_args:
        args.extend(container_args)

    final_cmd = " ".join(args)
    remote_exec(ssh, final_cmd, fail_on_error=True)
