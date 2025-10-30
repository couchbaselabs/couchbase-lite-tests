import json
import optparse
import sys
import paramiko


def fix_hostname(ip):
    """Ensure the remote machine has the correct hostname entry in /etc/hosts."""
    hostname_cmd = "hostname"
    result = run_remote_command(ip, hostname_cmd)

    if result:
        hostname = result
        add_host_cmd = f"echo '127.0.1.1 {hostname}' >> /etc/hosts"
        run_remote_command(ip, add_host_cmd)


def get_ips_from_config(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, "r") as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


def run_remote_command(ip, command):
    """Runs a command on the remote machine using Paramiko SSH."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(ip, username="root", password="couchbase")
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        return output.strip(), error.strip()

    except Exception as e:
        print(f"Error connecting to {ip}: {str(e)}")
        return None, str(e)

    finally:
        ssh.close()


def uninstall_sync_gateway(ip):
    """Uninstalls Sync Gateway and removes all configuration files from the given IP."""

    fix_hostname(ip)

    # Check if Sync Gateway service exists
    output, _ = run_remote_command(ip, "systemctl status sync_gateway")
    if "could not be found" in _.lower():
        print(f"Sync Gateway is not installed on {ip}. Skipping uninstallation.")
        return

    print(f"Stopping Sync Gateway on {ip}...")
    run_remote_command(ip, "sudo systemctl stop sync_gateway")

    print(f"Disabling Sync Gateway on {ip}...")
    output, error = run_remote_command(ip, "sudo systemctl disable sync_gateway")
    if "not found" in error.lower():
        print("Sync Gateway service already removed.")

    print(f"Removing Sync Gateway package and directories from {ip}...")
    run_remote_command(ip, "sudo apt-get remove --purge -y couchbase-sync-gateway")
    run_remote_command(
        ip,
        "sudo rm -rf /home/couchbase /home/sync_gateway /opt/couchbase-sync-gateway /opt/sg /tmp/couchbase-sync-gateway-enterprise_x86_64.deb",
    )

    print(f"Cleaning up remaining Sync Gateway files on {ip}...")
    run_remote_command(
        ip,
        "sudo rm -rf /etc/sync_gateway /var/lib/sync_gateway /var/log/sync_gateway /tmp/sg_logs /var/tmp/sglogs",
    )
    run_remote_command(ip, "sudo apt-get autoremove -y && sudo apt-get clean")

    print(f"Removing systemd service file on {ip}...")
    run_remote_command(ip, "sudo rm -f /usr/lib/systemd/system/sync_gateway.service")
    run_remote_command(
        ip, "sudo systemctl daemon-reload && sudo systemctl reset-failed"
    )

    print(f"Removing leftover package info on {ip}...")
    run_remote_command(ip, "sudo rm -rf /var/lib/dpkg/info/couchbase-sync-gateway.*")

    # Verify Sync Gateway removal
    output, _ = run_remote_command(ip, "systemctl status sync_gateway")
    if "could not be found" in _.lower():
        print(f"Sync Gateway successfully uninstalled from {ip}.")
    else:
        print(
            f"Sync Gateway service still exists on {ip}. Manual cleanup may be needed."
        )


def main():
    parser = optparse.OptionParser()
    parser.add_option(
        "-c",
        "--cluster-config",
        dest="cluster_config",
        help="Path to the cluster config JSON file",
        metavar="CLUSTER_CONFIG",
        default=None,
    )

    (options, args) = parser.parse_args()

    if not options.cluster_config:
        print("Usage: python uninstall_sync_gateway.py -c CLUSTER_CONFIG")
        sys.exit(1)

    # Fetch IPs from the cluster config and sync gateway config
    sync_gateway_ips = get_ips_from_config(options.cluster_config, "sync-gateways")

    for sync_gateway_ip in sync_gateway_ips:
        uninstall_sync_gateway(sync_gateway_ip)


if __name__ == "__main__":
    main()
