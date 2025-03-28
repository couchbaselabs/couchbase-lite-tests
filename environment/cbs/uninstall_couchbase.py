import json
import subprocess
import sys
from optparse import OptionParser
import paramiko


def fix_hostname(ip):
    """Ensure the remote machine has the correct hostname entry in /etc/hosts."""
    hostname_cmd = "hostname"
    result = run_remote_command(ip, hostname_cmd)

    if result:
        hostname = result
        add_host_cmd = f"echo '127.0.1.1 {hostname}' >> /etc/hosts"
        run_remote_command(ip, add_host_cmd)


def run_remote_command(ip, command):
    """Runs a command on a remote server via SSH and returns output & error."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(ip, username="root", password="couchbase")
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        return output.strip(), error.strip()
        
        # if error:
        #     print(f"Error executing command on {ip}: {error}")
        #     # sys.exit(1)
        
        # return output

    except Exception as e:
        print(f"Error connecting to {ip}: {str(e)}")
        sys.exit(1)

    finally:
        ssh.close()


def stop_couchbase_service(ip):
    """Stops Couchbase service and kills remaining processes."""
    print(f"Stopping Couchbase Server on {ip}...")
    run_remote_command(ip, "sudo systemctl stop couchbase-server")
    
    print(f"Killing remaining Couchbase processes on {ip}...")
    run_remote_command(ip, "ps aux | grep '[c]ouchbase' | awk '{print $2}' | xargs -r sudo kill -9")

    print(f"Disabling Couchbase service on {ip}...")
    output, error = run_remote_command(ip, "sudo systemctl disable couchbase-server")
    if "not found" in error.lower():
        print("Couchbase service already removed.")

def uninstall_couchbase_server(ips):
    """Uninstalls Couchbase Server from a list of remote machines."""
    for ip in ips:
        try:
            fix_hostname(ip)
            print(f"Checking if Couchbase is running on {ip}...")
            output, _ = run_remote_command(ip, "systemctl status couchbase-server")
            
            if "could not be found" in _.lower():
                print(f"Couchbase is not running on {ip}, skipping uninstallation.")
                continue
            
            # Stop service and remove files
            stop_couchbase_service(ip)
            run_remote_command(ip, "sudo rm -r /tmp/couchbase-server.deb /var/couchbase-configured /var/log/couchbase-setup.log /opt/configure-cluster.sh /opt/configure-node.sh || true")
            
            print(f"Removing Couchbase package on {ip}...")
            run_remote_command(ip, "sudo apt-get remove --purge couchbase-server -y")

            print(f"Removing Couchbase directories on {ip}...")
            run_remote_command(ip, "sudo rm -rf /opt/couchbase")

            print(f"Removing systemd service on {ip}...")
            run_remote_command(ip, "sudo rm -f /etc/systemd/system/couchbase-server.service /lib/systemd/system/couchbase-server.service")
            
            print(f"Cleaning up unused dependencies on {ip}...")
            run_remote_command(ip, "sudo apt-get autoremove -y")
            
            print(f"Removing Couchbase data directory on {ip}...")
            run_remote_command(ip, "sudo rm -rf /opt/couchbase")
            
            # Verify uninstallation
            output, _ = run_remote_command(ip, "systemctl status couchbase-server")

            if "could not be found" in _.lower():
                print(f"Couchbase successfully uninstalled on {ip}.")
            else:
                print(f"Failed to uninstall Couchbase on {ip}, service still running.")
        except Exception as e:
            print(f"Error on {ip}: {e}")


# Parse command line arguments using OptionParser
def parse_args():
    parser = OptionParser(usage="usage: %prog [options] config")
    parser.add_option("-c", "--config", dest="config", help="Path to the JSON config file", metavar="FILE")
    
    (options, args) = parser.parse_args()
    
    if not options.config:
        parser.error("Config file not specified")
    
    return options.config


# Load IPs from configuration file
def load_ips_from_config(config_path):
    with open(config_path, 'r') as file:
        config = json.load(file)
    return [server["hostname"] for server in config.get("couchbase-servers", [])]


if __name__ == "__main__":
    config_path = parse_args()

    # Load IPs from config file
    ips = load_ips_from_config(config_path)

    # Uninstall Couchbase Server
    uninstall_couchbase_server(ips)
