import json
import optparse
import subprocess
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

    if create_cert:
        print(f"Creating client certificate on {edge_server_ip}...")
        command = f"/opt/couchbase-edge-server/bin/couchbase-edge-server --create-cert CN={edge_server_ip} /opt/couchbase-edge-server/cert/certfile_tls /opt/couchbase-edge-server/cert/keyfile_tls"
        run_remote_command(edge_server_ip, command)
        subprocess.run(
            ["sshpass", "-p", "couchbase", "scp", f"root@{edge_server_ip}:/opt/couchbase-edge-server/cert/certfile_tls", "./config"],
            check=True)

    if mtls:
        mtls_key_path="/opt/couchbase-edge-server/cert/rootkey"
        mtls_cert_path="/opt/couchbase-edge-server/cert/rootcert"
        print(f"Creating root certificate on {edge_server_ip}...")
        command = f"openssl genrsa -out {mtls_key_path} 2048"
        run_remote_command(edge_server_ip, command)
        command=f"openssl req -x509 -new -nodes -key {mtls_key_path} -sha256 -days 365 -out {mtls_cert_path} -subj '/CN=Root'"
        run_remote_command(edge_server_ip, command)
        command="openssl genrsa -out /opt/couchbase-edge-server/cert/keyfile 2048"
        run_remote_command(edge_server_ip, command)
        command=f"openssl req -new -key  /opt/couchbase-edge-server/cert/keyfile -out  /opt/couchbase-edge-server/cert/server_csr -subj '/CN={edge_server_ip}'"
        run_remote_command(edge_server_ip, command)
        command=f"openssl x509 -req -in /opt/couchbase-edge-server/cert/server_csr -CA {mtls_cert_path} -CAkey {mtls_key_path} -CAcreateserial -out /opt/couchbase-edge-server/cert/certfile -days 365"
        run_remote_command(edge_server_ip, command)

    if database_path is not None:
        print("Setting up database directory...")
        run_remote_command(edge_server_ip, "sudo mkdir -p /opt/couchbase-edge-server/database")
        run_remote_command(edge_server_ip, "sudo chmod 755 -R /opt/couchbase-edge-server/database")
        run_remote_command(edge_server_ip, "sudo chown -R couchbase:couchbase /opt/couchbase-edge-server/database")
        print(f"Copying database file to {data_file_path}...")
        cmd_check_sshpass = "command -v sshpass || sudo apt-get update && sudo apt-get install -y sshpass"
        run_remote_command(edge_server_ip, cmd_check_sshpass)
        subprocess.run(
            ["sshpass", "-p", "couchbase", "scp", database_path, f"root@{edge_server_ip}:{data_file_path}"],
            check=True)
        cmd_check_unzip = "command -v unzip || sudo apt-get update && sudo apt-get install -y unzip"
        run_remote_command(edge_server_ip,cmd_check_unzip)
        run_remote_command(edge_server_ip, f"unzip -o {data_file_path} -d /opt/couchbase-edge-server/database")

    if user:
        print(f"Creating users.json  on {edge_server_ip}...")
        run_remote_command(edge_server_ip, "sudo mkdir -p /opt/couchbase-edge-server/users")
        run_remote_command(edge_server_ip, "sudo chmod 755 -R /opt/couchbase-edge-server/users")
        run_remote_command(edge_server_ip, "sudo chown -R couchbase:couchbase /opt/couchbase-edge-server/users")
        command = "/opt/couchbase-edge-server/bin/couchbase-edge-server --add-user /opt/couchbase-edge-server/users/users.json  admin_user --create --role admin --password password"
        run_remote_command(edge_server_ip, command)
    
    run_remote_command(edge_server_ip, f"sudo chmod 644 {config_file_path}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {config_file_path}")
    run_remote_command(edge_server_ip, f"sudo mkdir -p {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chmod 755 {log_dir}")
    run_remote_command(edge_server_ip, f"sudo chown -R couchbase:couchbase {log_dir}")
    run_remote_command(edge_server_ip, "sudo systemctl restart couchbase-edge-server")
    time.sleep(15)
    
    print("Checking if Couchbase Edge Server is running on port 59840...")
    output = run_remote_command(edge_server_ip, "systemctl status couchbase-edge-server")
    if "active (running)" in output:
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
