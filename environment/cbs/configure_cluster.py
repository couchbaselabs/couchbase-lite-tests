import json
import subprocess
import os
import optparse
import sys
import paramiko

# Function to execute a command remotely over SSH
def execute_remote_command(ip, command, password="couchbase"):
    ssh_command = f"sshpass -p {password} ssh root@{ip} '{command}'"
    print(f"Running command on {ip}: {command}")
    result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing command on {ip}: {result.stderr}")
        sys.exit(1)
    print(result.stdout)


def execute_remote_command(ip, command):
    try:
        # Create an SSH client
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add unknown host keys

        # Connect to the remote server
        ssh_client.connect(ip, username='root', password='couchbase')  # Adjust as necessary

        # Execute the command and capture the output
        stdin, stdout, stderr = ssh_client.exec_command(command)

        # Read and print stdout (console output)
        for line in iter(stdout.readline, ''):
            print(f"STDOUT: {line.strip()}")

        # Read and print stderr (error output)
        for line in iter(stderr.readline, ''):
            print(f"STDERR: {line.strip()}")

        # Wait for the command to finish
        stdout.channel.recv_exit_status()

        # Close the SSH connection
        ssh_client.close()
        
    except Exception as e:
        print(f"Error: {str(e)}")

# Function to copy the setup script to a remote server using SCP
def scp_to_remote(ip, script_path, script_location):
    try:
        subprocess.run(["sshpass", "-p", "couchbase", "scp", script_path, f"root@{ip}:{script_location}"], check=True)
        print(f"Successfully copied script to {ip}")
    except subprocess.CalledProcessError as e:
        print(f"Error copying script to {ip}: {e}")

def get_couchbase_server_ips(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]

# Deploy the setup script and execute it on each Couchbase server
def deploy_and_configure_cluster():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--cluster-config", dest="cluster_config", help="Path to the cluster config JSON file", metavar="CLUSTER_CONFIG", default=None)

    (options, args) = parser.parse_args()

    if not options.cluster_config:
        print("Usage: python configure_cluster.py -c CLUSTER_CONFIG")
        sys.exit(1)

    couchbase_servers = get_couchbase_server_ips(options.cluster_config, "couchbase-servers")

    script_location = "/opt/configure-cluster.sh"
    
    for ip in couchbase_servers:
        # Step 1: Copy the setup script to the remote server
        scp_to_remote(ip, "environment/cbs/configure-cluster.sh", script_location)
        
        # Step 2: Execute the setup script on the remote server
        execute_remote_command(ip, f'bash {script_location}')
    
    print("Couchbase cluster configuration complete.")

if __name__ == '__main__':
    deploy_and_configure_cluster()
