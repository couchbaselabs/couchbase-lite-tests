#!/usr/bin/env python3
import os
import subprocess
import sys

import click


@click.command()
@click.option("--repo-path", help="Path to an existing sync_gateway repo")
@click.option("--git-tag", help="Build tag (will clone/reset a local repo to this tag)")
def main(repo_path, git_tag):
    """Build Sync Gateway"""
    if bool(repo_path) == bool(git_tag):
        raise click.UsageError("Exactly one of --repo-path or --git-tag must be provided.")

    env_local_dir = os.path.dirname(os.path.abspath(__file__))
    output_bin = os.path.join(env_local_dir, "sync_gateway")

    if repo_path:
        repo_dir = os.path.abspath(repo_path)
        if not os.path.isdir(repo_dir):
            click.secho(f"Error: Repository path {repo_dir} does not exist.", fg="red")
            sys.exit(1)
    else:
        # We use a local clone
        repo_dir = os.path.join(env_local_dir, "sync_gateway_clone")
        repo_url = "https://github.com/couchbase/sync_gateway.git"

        if not os.path.exists(repo_dir):
            click.echo(f"Cloning {repo_url} into {repo_dir}...")
            subprocess.check_call(["git", "clone", repo_url, repo_dir])

        click.echo(f"Fetching updates and checking out {git_tag}...")
        subprocess.check_call(["git", "fetch", "--all", "--tags"], cwd=repo_dir)
        subprocess.check_call(["git", "reset", "--hard"], cwd=repo_dir)
        subprocess.check_call(["git", "checkout", git_tag], cwd=repo_dir)

    click.echo(f"Building sync_gateway in {repo_dir}...")
    build_cmd = ["go", "build", "-tags", "cb_sg_enterprise", "-o", output_bin, "."]

    try:
        subprocess.check_call(build_cmd, cwd=repo_dir)
        click.secho(f"Successfully built sync_gateway to {output_bin}", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"Error building sync_gateway: {e}", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
