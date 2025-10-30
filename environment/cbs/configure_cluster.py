import json
import optparse
import sys
import paramiko


# Function to copy the setup script to a remote server using SFTP
def scp_to_remote(
    ip, script_path, script_location, username="root", password="couchbase"
):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password)

        sftp = ssh.open_sftp()
        sftp.put(script_path, script_location)
        sftp.close()
        ssh.close()

        print(f"Successfully copied script to {ip}")

    except Exception as e:
        print(f"Error copying script to {ip}: {e}")


# Function to execute a remote command using SSH
def execute_remote_command(ip, command, username="root", password="couchbase"):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password)

        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        ssh.close()

        if error:
            print(f"Error executing command on {ip}: {error}")
        else:
            print(f"Command executed successfully on {ip}: {output}")

    except Exception as e:
        print(f"SSH command execution failed on {ip}: {e}")


def get_couchbase_server_ips(config_path, key):
    """Reads IPs from the config file."""
    with open(config_path, "r") as f:
        config_data = json.load(f)
    return [entry["hostname"] for entry in config_data.get(key, [])]


# Deploy the setup script and execute it on each Couchbase server
def deploy_and_configure_cluster():
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
        print("Usage: python configure_cluster.py -c CLUSTER_CONFIG")
        sys.exit(1)

    couchbase_servers = get_couchbase_server_ips(
        options.cluster_config, "couchbase-servers"
    )
    script_location = "/opt/configure-cluster.sh"

    for ip in couchbase_servers:
        # Step 1: Copy the setup script to the remote server
        # scp_to_remote(ip, "environment/cbs/configure-cluster.sh", script_location)
        scp_to_remote(ip, "environment/cbs/configure-cluster.sh", script_location)

        # Step 2: Execute the setup script on the remote server
        execute_remote_command(ip, f"bash {script_location}")

    print("Couchbase cluster configuration complete.")


if __name__ == "__main__":
    deploy_and_configure_cluster()
