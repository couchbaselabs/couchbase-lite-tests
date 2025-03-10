import json
import optparse
import os
import subprocess
import sys
import time
import paramiko


# async def ensure_sshpass(ip):
#     """Ensure sshpass is installed on the remote machine using asyncssh."""
#     print(f"Checking if sshpass is installed on {ip}...")

#     async with asyncssh.connect(ip, username='root', password='couchbase', known_hosts=None) as client:
#         result = await client.run(
#             "if ! command -v sshpass; then "
#             "sudo apt-get update && sudo apt-get install -y sshpass && "
#             "hash -r && exec bash; "
#             "fi"
#         )
        
#         if result.exit_status == 0:
#             print(f"sshpass is now installed on {ip}.")
#         else:
#             print(f"Failed to install sshpass on {ip}: {result.stderr}")
#             return False

#     return True


# # Function to run SSH commands on remote machine with password prompt handling
# def run_remote_command(ip, command, password="couchbase"):
#     """SSH into a remote machine and run the given command."""
#     ssh_command = f"/usr/bin/sshpass -p {password} ssh root@{ip} '{command}'"
#     print(f"Running command on {ip}: {command}")
#     result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
#     if result.returncode != 0:
#         print(f"Error executing command on {ip}: {result.stderr}")
#         sys.exit(1)
#     print(result.stdout)

def fix_hostname(ip):
    """Ensure the remote machine has the correct hostname entry in /etc/hosts."""
    hostname_cmd = "hostname"
    result = run_remote_command(ip, hostname_cmd)

    if result:
        hostname = result
        add_host_cmd = f"echo '127.0.1.1 {hostname}' >> /etc/hosts"
        run_remote_command(ip, add_host_cmd)

# def run_remote_command(ip, command, password="couchbase"):
#     """
#     Executes a command on a remote machine using paramiko.
#     """
#     print(f"Running command on {ip}: {command}")

#     try:
#         client = paramiko.SSHClient()
#         client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         client.connect(ip, username="root", password=password, timeout=10)

#         stdin, stdout, stderr = client.exec_command(command)
#         output = stdout.read().decode().strip()
#         error = stderr.read().decode().strip()

#         client.close()

#         if error:
#             print(f"Error executing command on {ip}: {error}")
#             sys.exit(1)
        
#         # print(output)
#         return output

#     except Exception as e:
#         print(f"Error executing command on {ip}: {e}")
#         sys.exit(1)

# # Function to copy a file using Paramiko SFTP
# def transfer_file(ip, local_path, remote_path, username="root", password="couchbase"):
#     try:
#         client = paramiko.SSHClient()
#         client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         client.connect(ip, username=username, password=password)

#         sftp = client.open_sftp()
#         print(f"Transferring {local_path} to {ip}:{remote_path}...")
#         sftp.put(local_path, remote_path)
#         sftp.close()
#         client.close()
#         print("File transfer completed.")
#     except Exception as e:
#         print(f"File transfer failed on {ip}: {e}")
#         sys.exit(1)


def get_ips_from_config(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


# def install_sync_gateway(sync_gateway_ip, sync_config, version, build):
#     """Installs and configures Sync Gateway on the given IP."""
#     fix_hostname(sync_gateway_ip)

#     # Define file paths
#     sg_package_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/{version}/{build}/couchbase-sync-gateway-enterprise_{version}-{build}_x86_64.deb"
#     sg_package_file = f"/tmp/couchbase-sync-gateway-enterprise_x86_64.deb"
    
#     # SSH into the VM to perform setup tasks before downloading
#     print(f"\nSSHing into {sync_gateway_ip} to prepare environment...")

#     # Download the Sync Gateway package
#     print(f"Downloading Sync Gateway package from {sg_package_url}...")
#     run_remote_command(sync_gateway_ip, f"wget -q {sg_package_url} -O {sg_package_file} && echo 'Done'")
    
#     # Install the package
#     print(f"Installing Sync Gateway package {sg_package_file}...")
#     run_remote_command(sync_gateway_ip, f"sudo dpkg -i {sg_package_file}")
    
#     # Stop Sync Gateway if running
#     print("Stopping Sync Gateway service...")
#     run_remote_command(sync_gateway_ip, "sudo systemctl stop sync_gateway")
    
#     print("Checking if Sync Gateway is stopped...")
#     sync_gateway_status = run_remote_command(sync_gateway_ip, "lsof -i :4985")
    
#     if sync_gateway_status:
#         print("Sync Gateway is still running. Exiting...")
#         sys.exit(1)

#     # Configure Sync Gateway
#     print(f"Adding Sync Gateway configuration for {sync_gateway_ip}...")
#     with open(sync_config, 'r') as f:
#         sync_gateway_config = json.load(f)

#     # Create necessary directories and set permissions
#     run_remote_command(sync_gateway_ip, "mkdir -p /opt/sg/logs")
#     run_remote_command(sync_gateway_ip, "sudo chown -R sync_gateway:sync_gateway /opt/sg/logs")
#     run_remote_command(sync_gateway_ip, "sudo chmod -R 750 /opt/sg/logs")

#     # Define remote config file path
#     config_path = "/home/sync_gateway/sync_gateway.json"
#     print(f"Writing config to {config_path}...")

#     # Transfer the Sync Gateway config file to the remote VM
#     print(f"Copying config file to remote VM {sync_gateway_ip}...")
#     transfer_file(sync_gateway_ip, sync_config, config_path)

#     time.sleep(15)

#     run_remote_command(sync_gateway_ip, f"sudo chown -R sync_gateway:sync_gateway {config_path}")
#     run_remote_command(sync_gateway_ip, f"sudo chmod 644 {config_path}")

#     # Start Sync Gateway with the new config file
#     print(f"Starting Sync Gateway with config file: {config_path} on {sync_gateway_ip}...")
#     run_remote_command(sync_gateway_ip, f"cat {config_path}")
#     run_remote_command(sync_gateway_ip, "sudo systemctl restart sync_gateway")

#     # Verify Sync Gateway is running on port 4985
#     print(f"Checking if Sync Gateway is running on {sync_gateway_ip}...")
#     sync_gateway_status = run_remote_command(sync_gateway_ip, "lsof -i :4985")

#     if sync_gateway_status:
#         print(f"Sync Gateway is running successfully on {sync_gateway_ip}.")
#     else:
#         print(f"Sync Gateway failed to start on {sync_gateway_ip}. Exiting...")
#         sys.exit(1)

    # # Verify that Sync Gateway is stopped
    # print("Checking if Sync Gateway is stopped...")
    # sync_gateway_status = subprocess.run(["sshpass", "-p", "couchbase", "ssh", f"root@{sync_gateway_ip}", "lsof -i :4985"], capture_output=True, text=True)
    # if sync_gateway_status.stdout:
    #     print("Sync Gateway is still running. Exiting...")
    #     sys.exit(1)
    
    # # Configure Sync Gateway
    # print(f"Adding Sync Gateway configuration for {sync_gateway_ip}...")
    # with open(sync_config, 'r') as f:
    #     sync_gateway_config = json.load(f)

    # # SSH into the remote VM and create the necessary directories for logs
    # run_remote_command(sync_gateway_ip, "mkdir -p /opt/sg/logs")
    # run_remote_command(sync_gateway_ip, "sudo chown -R sync_gateway:sync_gateway /opt/sg/logs")
    # run_remote_command(sync_gateway_ip, "sudo chmod -R 750 /opt/sg/logs")

    # # Write config to the config file path on the remote machine
    # config_path = f"/home/sync_gateway/sync_gateway.json"
    # print(f"Writing config to {config_path}...")

    # # Transfer the sync_gateway config file to the remote VM
    # print(f"Copying config file to remote VM {sync_gateway_ip}...")
    # subprocess.run(["sshpass", "-p", "couchbase", "scp", sync_config, f"root@{sync_gateway_ip}:{config_path}"], check=True)

    # time.sleep(15)

    # run_remote_command(sync_gateway_ip, f"sudo chown -R sync_gateway:sync_gateway {config_path}")
    # run_remote_command(sync_gateway_ip, f"sudo chmod 644 {config_path}")

    # # Start Sync Gateway with the new config file
    # print(f"Starting Sync Gateway with config file: {config_path} on {sync_gateway_ip}...")
    # run_remote_command(sync_gateway_ip, f"cat {config_path}")
    
    # run_remote_command(sync_gateway_ip, f"sudo systemctl restart sync_gateway")

    # # Verify that Sync Gateway is running on port 4985
    # print(f"Checking if Sync Gateway is running on {sync_gateway_ip}...")
    # sync_gateway_status = subprocess.run(["sshpass", "-p", "couchbase", "ssh", f"root@{sync_gateway_ip}", "lsof -i :4985"], capture_output=True, text=True)
    # if sync_gateway_status.stdout:
    #     print(f"Sync Gateway is running successfully on {sync_gateway_ip}.")
    # else:
    #     print(f"Sync Gateway failed to start on {sync_gateway_ip}. Exiting...")
    #     sys.exit(1)

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
    output, _ = run_remote_command(sync_gateway_ip, "dpkg -l | grep sync-gateway")
    if output:
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

    if "could not be found" in _.lower():
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
