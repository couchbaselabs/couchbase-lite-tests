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


def uninstall_edge_server(ip, password="couchbase"):
    """ Uninstalls Edge Server and removes all configuration files for it on the given IP."""

    # Check if the Couchbase Edge Server is running
    result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} 'sudo systemctl status couchbase-edge-server'", shell=True,
                           capture_output=True, text=True)
    if "Unit couchbase-edge-server.service could not be found." in result.stderr:
        print(f"Edge server not found as a process on {ip}")
        return

    print("Checking if Couchbase Edge Server is running...")
    result = subprocess.run(
        f"sshpass -p {password} ssh root@{ip} 'pgrep -f /opt/couchbase-edge-server/bin/couchbase-edge-server'",
        shell=True, capture_output=True, text=True
    )

    if result.stdout.strip():
        print("Couchbase Edge Server is running. Stopping the process...")
        # Stop the process using the PID stored in /tmp
        # run_remote_command(ip, "sudo kill $(sudo pgrep couchbase) && sudo rm -f /tmp/edge_server.pid")
        run_remote_command(ip, "sudo systemctl stop couchbase-edge-server")
        run_remote_command(ip, "sudo systemctl disable couchbase-edge-server")
    else:
        print("Couchbase Edge Server process is not running.")

    # Remove Couchbase Edge Server package
    print("Removing Couchbase Edge Server package and related files...")
    run_remote_command(
        ip,
        "sudo apt-get remove --purge couchbase-edge-server -y && sudo rm -rf *.cblite2 /opt/couchbase-edge-server /tmp/couchbase-edge-server.deb /home/couchbase/"
    )

    # Remove unnecessary files and directories
    print("Cleaning up additional directories and logs...")
    run_remote_command(ip, "sudo rm -rf /var/log/couchbase-edge-server /tmp/EdgeServerLog")

    # Perform system cleanup
    print("Performing system cleanup...")
    run_remote_command(ip, "sudo apt-get autoremove -y && sudo apt-get clean")

    # Remove any leftover package information
    run_remote_command(ip, "sudo rm -rf /var/lib/dpkg/info/couchbase-*")

    # Verify uninstallation
    print("Verifying uninstallation of Couchbase Edge Server...")
    result = subprocess.run(
        f"sshpass -p {password} ssh root@{ip} 'pgrep -f /opt/couchbase-edge-server/bin/couchbase-edge-server'",
        shell=True, capture_output=True, text=True
    )
    if not result.stdout.strip():
        print("Couchbase Edge Server is successfully uninstalled.")
    else:
        print("Couchbase Edge Server process is still present. Uninstallation may not be complete.")


def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--cluster-config", dest="cluster_config", help="Path to the cluster config JSON file", metavar="CLUSTER_CONFIG", default=None)

    (options, args) = parser.parse_args()

    if not options.cluster_config:
        print("Usage: python uninstall_edge_server.py -c CLUSTER_CONFIG")
        sys.exit(1)

    # Fetch IPs from the cluster config and sync gateway config
    edge_server_ips = get_ips_from_config(options.cluster_config, "edge-servers")

    for edge_server_ip in edge_server_ips:
        uninstall_edge_server(edge_server_ip)


if __name__ == "__main__":
    main()