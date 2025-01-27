import json
import optparse
import os
import subprocess
import sys
import time


# Function to run SSH commands on remote machine with password prompt handling
def run_remote_command(ip, command, password="couchbase"):
    """SSH into a remote machine and run the given command."""
    ssh_command = f"sshpass -p {password} ssh root@{ip} '{command}'"
    print(f"Running command on {ip}: {command}")
    result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing command on {ip}: {result.stderr}")
        sys.exit(1)
    print(result.stdout)


def get_ips_from_config(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


def uninstall_sync_gateway(ip):
    """ Uninstalls Sync Gateway and removes all configuration files for it on the given IP."""

    # Stop Sync Gateway if running
    result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} 'sudo systemctl status sync_gateway'", shell=True, capture_output=True, text=True)
    if "Unit sync_gateway.service could not be found." in result.stderr:
        print(f"Sync Gateway not found as a process on {ip}")
        return

    run_remote_command(ip, "sudo systemctl stop sync_gateway")

    run_remote_command(ip, "sudo systemctl disable sync_gateway")

    # Remove Sync Gateway package
    run_remote_command(ip, "sudo apt-get remove --purge sync-gateway && rm -rf /home/sync_gateway/ /opt/couchbase-sync-gateway/ /opt/sg/ /tmp/couchbase-sync-gateway-enterprise_x86_64.deb || true")

    # Remove unnecessary files and directories
    run_remote_command(ip, "sudo rm -rf /etc/sync_gateway /var/lib/sync_gateway /var/log/sync_gateway /tmp/sg_logs /var/tmp/sglogs")
    run_remote_command(ip, "sudo apt-get autoremove -y && sudo apt-get clean || true")

    # Remove systemd service file
    run_remote_command(ip, "sudo rm -f /usr/lib/systemd/system/sync_gateway.service")
    run_remote_command(ip, "sudo systemctl daemon-reload && sudo systemctl reset-failed")

    # Remove any leftover package information
    run_remote_command(ip, "sudo rm -rf /var/lib/dpkg/info/couchbase-sync-gateway.*")

    # Verify that Sync Gateway is uninstalled
    result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} 'sudo systemctl status sync_gateway'", shell=True, capture_output=True, text=True)

    if "Unit sync_gateway.service could not be found." in result.stderr:
        print("Sync Gateway is uninstalled or service is not found.")
    else:
        print("Sync Gateway service is still present.")


def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--cluster-config", dest="cluster_config", help="Path to the cluster config JSON file", metavar="CLUSTER_CONFIG", default=None)

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
