import json
import optparse
import sys
import time
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
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


def run_remote_command(ip, command):
    """Runs a command on a remote server via SSH and returns output & error."""
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

def transfer_file(ip, local_path, remote_path):
    """Transfers a file to a remote server using SCP over SSH."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(ip, username="root", password="couchbase")
        sftp = ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        print(f"File {local_path} copied to {remote_path}")
    except Exception as e:
        print(f"Error copying file to {ip}: {str(e)}")
    finally:
        ssh.close()

def install_sync_gateway(sync_gateway_ip, sync_config, version, build):
    """Installs and configures Sync Gateway on the given IP."""
    fix_hostname(sync_gateway_ip)

    # Define package URL and paths
    sg_package_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/{version}/{build}/couchbase-sync-gateway-enterprise_{version}-{build}_x86_64.deb"
    sg_package_file = "/tmp/couchbase-sync-gateway-enterprise_x86_64.deb"

    print(f"\nPreparing to install Sync Gateway on {sync_gateway_ip}...")

    # Check if Sync Gateway is already installed
    output, _ = run_remote_command(sync_gateway_ip, "systemctl status sync_gateway")
    if "could not be found" not in _.lower():
        print("Sync Gateway is already installed. Uninstall first if needed.")
        return

    # Download Sync Gateway package
    print(f"Downloading Sync Gateway package from {sg_package_url}...")
    output, error = run_remote_command(sync_gateway_ip, f"wget -q {sg_package_url} -O {sg_package_file}")

    if error:
        print(f"Error downloading Sync Gateway: {error}")
        return

    print("Installing Sync Gateway package...")
    output, error = run_remote_command(sync_gateway_ip, f"sudo dpkg -i {sg_package_file}")
    if "errors" in error.lower():
        print(f"Installation failed: {error}")
        return

    # Stop Sync Gateway if running
    print("Stopping Sync Gateway service if running...")
    run_remote_command(sync_gateway_ip, "sudo systemctl stop sync_gateway")

    # Ensure service is stopped
    output, _ = run_remote_command(sync_gateway_ip, "lsof -i :4985")
    if output:
        print("Sync Gateway is still running. Exiting...")
        sys.exit(1)

    # Transfer the configuration file
    config_path = "/home/sync_gateway/sync_gateway.json"
    print(f"Copying Sync Gateway config to {sync_gateway_ip}...")
    transfer_file(sync_gateway_ip, sync_config, config_path)

    # Set correct ownership and permissions
    print("Setting permissions for the config file...")
    run_remote_command(sync_gateway_ip, f"sudo chown sync_gateway:sync_gateway {config_path}")
    run_remote_command(sync_gateway_ip, f"sudo chmod 644 {config_path}")

    # Create necessary directories with correct permissions
    print("Creating logs directory...")
    run_remote_command(sync_gateway_ip, "sudo mkdir -p /opt/sg/logs")
    run_remote_command(sync_gateway_ip, "sudo chown -R sync_gateway:sync_gateway /opt/sg/logs")
    run_remote_command(sync_gateway_ip, "sudo chmod -R 750 /opt/sg/logs")

    time.sleep(5)

    # Restart Sync Gateway service
    print("Starting Sync Gateway...")
    run_remote_command(sync_gateway_ip, "sudo systemctl restart sync_gateway")

    # Verify Sync Gateway is running
    print("Checking if Sync Gateway is running...")
    output, _ = run_remote_command(sync_gateway_ip, "systemctl status sync_gateway")

    if "active (running)" not in output:
        print(f"Sync Gateway failed to start on {sync_gateway_ip}. Exiting...")
        sys.exit(1)
    else:
        print(f"Sync Gateway is running successfully on {sync_gateway_ip}.")
        

def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--cluster-config", dest="cluster_config", help="Path to the cluster config JSON file", metavar="CLUSTER_CONFIG", default=None)
    parser.add_option("-s", "--sync-config", dest="sync_config", help="Path to the Sync Gateway config JSON file", metavar="SYNC_CONFIG", default=None)
    parser.add_option("-v", "--version", dest="version", help="Sync Gateway version", metavar="VERSION", default=None)
    parser.add_option("-b", "--build", dest="build", help="Sync Gateway build number", metavar="BUILD", default=None)

    (options, args) = parser.parse_args()

    if not options.cluster_config or not options.sync_config or not options.version or not options.build:
        print("Usage: python install_sync_gateway.py -c CLUSTER_CONFIG -s SYNC_CONFIG -v VERSION -b BUILD_NUMBER")
        sys.exit(1)

    # Fetch IPs from the cluster config and sync gateway config
    sync_gateway_ips = get_ips_from_config(options.cluster_config, "sync-gateways")

    for sync_gateway_ip in sync_gateway_ips:
        install_sync_gateway(sync_gateway_ip, options.sync_config, options.version, options.build)


if __name__ == "__main__":
    main()
