import json
import optparse
import os
import subprocess
import sys
import time
import paramiko
from distutils.command.build import build

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


def run_remote_command(ip, command, username="root", password="couchbase"):
    """SSH into a remote machine and run the given command using Paramiko."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password)
        print(f"Running command on {ip}: {command}")
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        client.close()
        
        if error:
            if "Created symlink" in error:
                print(f"Warning: {error}")
            else:
                print(f"Error executing command on {ip}: {error}")
                sys.exit(1)
        
        print(output)
        return output
    except Exception as e:
        print(f"SSH connection failed: {e}")
        sys.exit(1)


def copy_file_to_remote(ip, local_path, remote_path, username="root", password="couchbase"):
    """Copies a file from the local machine to the remote server using SFTP."""
    try:
        transport = paramiko.Transport((ip, 22))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        print(f"Copying {local_path} to {ip}:{remote_path}")
        sftp.put(local_path, remote_path)
        sftp.close()
        transport.close()
    except Exception as e:
        print(f"File transfer failed: {e}")
        sys.exit(1)


def install_edge_server(edge_server_ip, edge_server_config, version, build, create_cert, database_path, mtls, user):
    """Installs and configures Edge Server on the given IP."""

    fix_hostname(edge_server_ip)

    package_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-edge-server/{version}/{build}/couchbase-edge-server_{version}-{build}_amd64.deb"
    package_file = "/tmp/couchbase-edge-server.deb"
    config_file_path = "/opt/couchbase-edge-server/etc/config.json"
    data_file_path = "/opt/couchbase-edge-server/database/db.cblite2.zip"
    log_dir = "/tmp/EdgeServerLog"
    
    print(f"\nSSHing into {edge_server_ip} to prepare environment...")
    run_remote_command(edge_server_ip, f"wget -q {package_url} -O {package_file}")
    run_remote_command(edge_server_ip, f"sudo dpkg -i {package_file}")
    run_remote_command(edge_server_ip, "sudo systemctl stop couchbase-edge-server")
    time.sleep(15)
    
    print(f"Writing config to {config_file_path}...")
    copy_file_to_remote(edge_server_ip, edge_server_config, config_file_path)
    
    if create_cert or mtls:
        run_remote_command(edge_server_ip, "sudo mkdir -p /opt/couchbase-edge-server/cert")
        run_remote_command(edge_server_ip, "sudo chmod 755 -R /opt/couchbase-edge-server/cert")
        run_remote_command(edge_server_ip, "sudo chown -R couchbase:couchbase /opt/couchbase-edge-server/cert")
    
    if database_path:
        run_remote_command(edge_server_ip, "sudo mkdir -p /opt/couchbase-edge-server/database")
        run_remote_command(edge_server_ip, "sudo chmod 755 -R /opt/couchbase-edge-server/database")
        run_remote_command(edge_server_ip, "sudo chown -R couchbase:couchbase /opt/couchbase-edge-server/database")
        copy_file_to_remote(edge_server_ip, database_path, data_file_path)
        run_remote_command(edge_server_ip, f"unzip -o {data_file_path} -d /opt/couchbase-edge-server/database")
    
    run_remote_command(edge_server_ip, f"sudo chmod 644 {config_file_path}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {config_file_path}")
    run_remote_command(edge_server_ip, f"sudo mkdir -p {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chmod 755 {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {log_dir}")
    run_remote_command(edge_server_ip, "sudo systemctl restart couchbase-edge-server")
    time.sleep(15)
    
    print("Checking if Couchbase Edge Server is running on port 59840...")
    output = run_remote_command(edge_server_ip, "systemctl status couchbase-edge-server")
    if "Started couchbase-edge-server.service" in output:
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
    parser.add_option("-d", "--database", dest="database", help="Edge Server database", metavar="DATABASE", default=None)
    parser.add_option("--create-cert", dest="create_cert", action="store_true",
                      help="Create a server certificate", default=False)
    parser.add_option("--mtls", dest="mtls", action="store_true",
                      help="Create a root certificate", default=False)
    # by default: admin_user:password.
    parser.add_option("-u", "--user", dest="user", help="Create default admin user", action="store_true",
                      default=False)
    (options, args) = parser.parse_args()

    if not options.cluster_config or not options.edge_server_config or not options.version or not options.build:
        print("Usage: python install_edge_server.py -c CLUSTER_CONFIG -e EDGE_SERVER_CONFIG -v VERSION -b BUILD_NUMBER")
        sys.exit(1)

    if options.mtls:
        options.create_cert=True

    # Fetch edge server IPs from the cluster config
    edge_server_ips = get_ips_from_config(options.cluster_config, "edge-servers")
    for edge_server_ip in edge_server_ips:
        install_edge_server(edge_server_ip, options.edge_server_config, options.version, options.build,options.create_cert,options.database,options.mtls,options.user)


if __name__ == "__main__":
    main()
