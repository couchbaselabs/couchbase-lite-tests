import json
import subprocess
import sys
from optparse import OptionParser


# Function to run SSH commands on remote machine with password prompt handling
def run_remote_command(ip, command, password="couchbase"):
    # Use 'sshpass' to provide password for SSH commands
    ssh_command = f"sshpass -p {password} ssh root@{ip} '{command}'"
    print(f"Running command on {ip}: {command}")
    result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error executing command on {ip}: {result.stderr}")
        sys.exit(1)
    print(result.stdout)


# Function to stop Couchbase Server service and kill any running processes
def stop_couchbase_service(ip):
    stop_service_command = "sudo systemctl stop couchbase-server"
    # Check if Couchbase is running and stop it
    run_remote_command(ip, stop_service_command)
    
    # Check if Couchbase processes are still running, and kill them if necessary
    kill_process_command = "ps aux | grep '[c]ouchbase' | awk '{print $2}' | xargs -r sudo kill -9"
    run_remote_command(ip, kill_process_command)


# Function to uninstall Couchbase Server
def uninstall_couchbase_server(ips):
    for ip in ips:
        try:
            # Check if Couchbase is running
            result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} 'ps aux | grep -v grep | grep couchbase'", shell=True, capture_output=True, text=True)
            if not result.stdout:
                print(f"Couchbase not found as a process on {ip}")
                continue

            # Stop Couchbase service and kill any remaining processes
            stop_couchbase_service(ip)

            # Delete the .deb file and config file
            delete_file = "sudo rm -r /tmp/couchbase-server.deb /var/couchbase-configured /var/log/couchbase-setup.log /opt/configure-cluster.sh /opt/configure-node.sh || true"
            run_remote_command(ip, delete_file)

            # Remove Couchbase Server package
            remove_package_command = "sudo apt-get remove --purge couchbase-server -y"
            run_remote_command(ip, remove_package_command)

            # Clean up unused dependencies
            clean_up_command = "sudo apt-get autoremove -y"
            run_remote_command(ip, clean_up_command)

            # Force removal of Couchbase data directory (even if not empty)
            remove_data_command = "sudo rm -rf /opt/couchbase"
            run_remote_command(ip, remove_data_command)

            # Check if Couchbase is still running
            result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} 'ps aux | grep -v grep | grep couchbase'", shell=True, capture_output=True, text=True)
            if not result.stdout:
                print(f"Couchbase successfully uninstalled on {ip}")
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
