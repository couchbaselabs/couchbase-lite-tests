import json
import optparse
import os
import subprocess
import sys
import time
import paramiko


def get_ips_from_config(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


def fix_hostname(ip):
    """Ensure the remote machine has the correct hostname entry in /etc/hosts."""
    hostname_cmd = "hostname"
    result = run_remote_command(ip, hostname_cmd)

    if result:
        hostname = result
        add_host_cmd = f"echo '127.0.1.1 {hostname}' >> /etc/hosts"
        run_remote_command(ip, add_host_cmd)


def run_remote_command(ip, command, password="couchbase"):
    """Executes a command on the remote machine using SSH."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username="root", password=password, timeout=10)
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        client.close()
        if error:
            return error.strip()
        return output.strip()
    except Exception as e:
        return str(e)


def uninstall_edge_server(ip, password="couchbase"):
    """ Uninstalls Edge Server and removes all configuration files for it on the given IP. """
    
    fix_hostname(ip)

    # Check if Couchbase Edge Server is installed
    result = run_remote_command(ip, "sudo systemctl status couchbase-edge-server", password)
    if "could not be found" in result:
        print(f"Edge server not found as a process on {ip}")
        return
    
    print("Checking if Couchbase Edge Server is running...")
    result = run_remote_command(ip, "pgrep -f /opt/couchbase-edge-server/bin/couchbase-edge-server", password)
    
    if result:
        print("Couchbase Edge Server is running. Stopping the process...")
        run_remote_command(ip, "sudo systemctl stop couchbase-edge-server", password)
        run_remote_command(ip, "sudo systemctl disable couchbase-edge-server", password)
    else:
        print("Couchbase Edge Server process is not running.")
    
    # Remove Couchbase Edge Server package and related files
    print("Removing Couchbase Edge Server package and related files...")
    run_remote_command(
        ip,
        "sudo apt-get remove --purge couchbase-edge-server -y && "
        "sudo rm -rf *.cblite2 /opt/couchbase-edge-server /tmp/couchbase-edge-server.deb /home/couchbase/",
        password
    )
    
    # Remove logs and directories
    print("Cleaning up additional directories and logs...")
    run_remote_command(ip, "sudo rm -rf /var/log/couchbase-edge-server /tmp/EdgeServerLog", password)
    
    # Perform system cleanup
    print("Performing system cleanup...")
    run_remote_command(ip, "sudo apt-get autoremove -y && sudo apt-get clean", password)
    
    # Remove leftover package information
    run_remote_command(ip, "sudo rm -rf /var/lib/dpkg/info/couchbase-*", password)
    
    # Verify uninstallation
    print("Verifying uninstallation of Couchbase Edge Server...")
    result = run_remote_command(ip, "pgrep -f /opt/couchbase-edge-server/bin/couchbase-edge-server", password)
    if not result:
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