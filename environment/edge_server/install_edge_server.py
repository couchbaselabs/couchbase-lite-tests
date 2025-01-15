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


def install_edge_server(edge_server_ip, edge_server_config, version, build):
    """Installs and configures Edge Server on the given IP."""
    # Define file paths
    package_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-edge-server/{version}/{build}/couchbase-edge-server_{version}-{build}_amd64.deb"
    package_file = "/tmp/couchbase-edge-server.deb"
    config_file_path = "/opt/couchbase-edge-server/config/config.json"
    log_dir = "/tmp/EdgeServerLog"

    # SSH into the VM
    print(f"\nSSHing into {edge_server_ip} to prepare environment...")

    # Download the Couchbase Edge Server package
    print(f"Downloading Couchbase Edge Server package from {package_url}...")
    run_remote_command(edge_server_ip, f"wget {package_url} -O {package_file}")

    # Install the package
    print(f"Installing Couchbase Edge Server package {package_file}...")
    run_remote_command(edge_server_ip, f"sudo dpkg -i {package_file}")

    # Make the server executable
    print("Making Couchbase Edge Server binary executable...")
    run_remote_command(edge_server_ip, "sudo chmod +x /opt/couchbase-edge-server/bin/couchbase-edge-server")

    # Create and set permissions for config directory
    print("Setting up config directory...")
    run_remote_command(edge_server_ip, "sudo mkdir -p /opt/couchbase-edge-server/config")
    run_remote_command(edge_server_ip, "sudo chmod 755 -R /opt/couchbase-edge-server/config")

    # Copy the configuration file to the remote VM
    print(f"Copying config file to {config_file_path}...")
    subprocess.run(["sshpass", "-p", "couchbase", "scp", edge_server_config, f"root@{edge_server_ip}:{config_file_path}"], check=True)

    # Set permissions for the configuration file
    print("Setting permissions for the config file...")
    run_remote_command(edge_server_ip, f"sudo chmod 644 {config_file_path}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {config_file_path}")

    # Create and set permissions for the log directory
    print(f"Creating and configuring log directory at {log_dir}...")
    run_remote_command(edge_server_ip, f"sudo mkdir -p {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chmod 755 {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {log_dir}")

    # Start Couchbase Edge Server with the config file
    print(f"Starting Couchbase Edge Server with config file {config_file_path}...")
    run_remote_command(edge_server_ip, f"nohup /opt/couchbase-edge-server/bin/couchbase-edge-server --verbose --config {config_file_path} > /tmp/edge_server.log 2>&1 & echo $! > /tmp/edge_server.pid")

    time.sleep(15)

    # Verify that Couchbase Edge Server is running on port 59840
    print("Checking if Couchbase Edge Server is running on port 59840...")
    edge_server_status = subprocess.run(["sshpass", "-p", "couchbase", "ssh", f"root@{edge_server_ip}", "lsof -i :59840"], capture_output=True, text=True)
    if edge_server_status.stdout:
        print(f"Couchbase Edge Server is running successfully on {edge_server_ip}.")
    else:
        print(f"Couchbase Edge Server failed to start on {edge_server_ip}. Exiting...")
        sys.exit(1)


def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--cluster-config", dest="cluster_config", help="Path to the cluster config JSON file", metavar="CLUSTER_CONFIG", default=None)
    parser.add_option("-e", "--edge-server-config", dest="edge_server_config", help="Path to the Edge server config JSON file", metavar="EDGE_SERVER_CONFIG", default=None)
    parser.add_option("-v", "--version", dest="version", help="Edge Server version", metavar="VERSION", default=None)
    parser.add_option("-b", "--build", dest="build", help="Edge Server build number", metavar="BUILD", default=None)

    (options, args) = parser.parse_args()

    if not options.cluster_config or not options.edge_server_config or not options.version or not options.build:
        print("Usage: python install_edge_server.py -c CLUSTER_CONFIG -e EDGE_SERVER_CONFIG -v VERSION -b BUILD_NUMBER")
        sys.exit(1)

    # Fetch edge server IPs from the cluster config
    edge_server_ips = get_ips_from_config(options.cluster_config, "edge-servers")

    for edge_server_ip in edge_server_ips:
        install_edge_server(edge_server_ip, options.edge_server_config, options.version, options.build)


if __name__ == "__main__":
    main()
