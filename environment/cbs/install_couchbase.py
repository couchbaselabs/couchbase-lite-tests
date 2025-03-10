import json
import requests
import subprocess
import sys
import time
from bs4 import BeautifulSoup
from optparse import OptionParser
import paramiko

LATESTBUILDS_BASE_URL = "http://latestbuilds.service.couchbase.com/builds"

RELEASES = {
    'spock': '5.0.0',
    'vulcan': '5.5.6',
    'alice': '6.0.4',
    'mad-hatter': '6.5.0',
    'cheshire-cat': '7.0.0',
    'neo': '7.1.0',
    'elixir': '7.2.0',
    'trinity': '7.6.0',
    'cypher': '7.7.0',
    'morpheus': '8.0.0'
}

DEFAULT_VERSION = "7.6.2"
DEFAULT_BUILD = "3721"


# Function to map version to codename
def get_codename(version):
    # Define the versions and corresponding codenames in sorted order
    version_mappings = [
        ('5.0', 'spock'),
        ('5.5', 'vulcan'),
        ('6.0', 'alice'),
        ('6.5', 'mad-hatter'),
        ('7.0', 'cheshire-cat'),
        ('7.1', 'neo'),
        ('7.2', 'elixir'),
        ('7.6', 'trinity'),
        ('7.7', 'cypher'),
        ('8.0', 'morpheus'),
        ('8.1', 'magma-preview')
    ]
    
    # Convert the version string to a tuple (major, minor) for easy comparison
    major_minor_version = tuple(map(int, version.split('.')[:2]))

    # Loop through the mappings and find where the version lies
    for i in range(len(version_mappings) - 1):
        lower_version = tuple(map(int, version_mappings[i][0].split('.')))
        upper_version = tuple(map(int, version_mappings[i + 1][0].split('.')))

        # Check if the version is within the range
        if lower_version <= major_minor_version < upper_version:
            return version_mappings[i][1]

    # If the version is greater than or equal to the last entry, return its codename
    return version_mappings[-1][1]  # Default to the last codename for versions >= 8.1


# Function to get the download URL based on version and build
def get_download_url(version=None, build=None):
    # If no version and build are specified, use default version and build
    if not version and not build:
        version = DEFAULT_VERSION
        build = DEFAULT_BUILD
    
    codename = get_codename(version)
    if codename is None:
        raise Exception(f"Unknown version: {version}")
    
    print(f"Using codename {codename} for version {version}")

    if build:
        # If build is provided, return the specific build URL
        return f"{LATESTBUILDS_BASE_URL}/latestbuilds/couchbase-server/{codename}/{build}/couchbase-server-enterprise_{version}-{build}-linux_amd64.deb"
    else:
        # If build is not specified, fetch the latest build
        latest_url = f"{LATESTBUILDS_BASE_URL}/latestbuilds/couchbase-server/{codename}/"
        print(f"Fetching latest builds from {latest_url}")
        
        try:
            response = requests.get(latest_url)
            response.raise_for_status()  # Raise an exception for bad HTTP responses
            
            # Use BeautifulSoup to parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            build_number = None

            # Search for links that contain 'build/' and extract the build number
            for link in soup.find_all('a', href=True):
                if 'build/' in link['href']:
                    build_number = link['href'].split('build/')[1].split('/')[0]
                    break
            
            if build_number:
                print(f"Latest build number: {build_number}")
                return get_download_url(version, build_number)
            else:
                raise Exception("Failed to extract build number from the latest builds page.")
        
        except requests.exceptions.RequestException as e:
            print(f"Error fetching the latest build page: {e}")
            raise

def fix_hostname(ip):
    """Ensure the remote machine has the correct hostname entry in /etc/hosts."""
    hostname_cmd = "hostname"
    result = run_remote_command(ip, hostname_cmd)

    if result:
        hostname = result.strip()
        add_host_cmd = f"echo '127.0.1.1 {hostname}' >> /etc/hosts"
        run_remote_command(ip, add_host_cmd)

# async def ensure_sshpass(ip):
#     """Ensure sshpass is installed on the remote machine using asyncssh."""
#     print(f"Checking if sshpass is installed on {ip}...")

#     async with asyncssh.connect(ip, username='root', password='couchbase', known_hosts=None) as client:
#         result = await client.run(
#             "if ! command -v sshpass; then "
#             "sudo -n apt-get update && "
#             "DEBIAN_FRONTEND=noninteractive sudo -n apt-get install -y sshpass; "
#             "fi",
#             check=True
#         )

#         if result.exit_status == 0:
#             print(f"✅ sshpass is now installed on {ip}.")
#             return True
#         else:
#             print(f"❌ Failed to install sshpass on {ip}: {result.stderr}")
#             return False

# def find_sshpass(ip, password="couchbase"):
#     """Find sshpass dynamically on the remote machine."""
#     ssh_command = f"/usr/bin/sshpass -p {password} ssh -o StrictHostKeyChecking=no root@{ip} 'export PATH=$PATH:/usr/local/bin:/usr/bin && which sshpass'"

#     remote_check = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
#     if remote_check.returncode == 0 and remote_check.stdout.strip():
#         remote_sshpass = remote_check.stdout.strip()
#         print(f"✅ Found sshpass on {ip} at: {remote_sshpass}")
#         return remote_sshpass
#     else:
#         print(f"❌ sshpass not found on {ip}. STDERR:\n{remote_check.stderr}")
#         sys.exit(1)

# def find_sshpass(ip):
#     """Finds the path of sshpass dynamically."""
#     result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} command -v sshpass", shell=True, capture_output=True, text=True)
#     if result.returncode == 0:
#         return result.stdout.strip()  # Return the sshpass path
#     return None

def run_remote_command(ip, command, password="couchbase"):
    """
    Executes a command on a remote machine using paramiko.
    """
    print(f"Running command on {ip}: {command}")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username="root", password=password, timeout=10)

        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        client.close()

        if error:
            if "Created symlink" in error:
                print(f"Warning: {error}")
            else:
                print(f"Error executing command on {ip}: {error}")
                sys.exit(1)
        
        # print(output)
        return output

    except Exception as e:
        print(f"Error executing command on {ip}: {e}")
        sys.exit(1)

# # Function to run SSH commands on remote machine with password prompt handling
# def run_remote_command(ip, command, password="couchbase"):
#     # Use 'sshpass' to provide password for SSH commands
#     sshpass_path = find_sshpass() or "/usr/bin/sshpass"
#     ssh_command = f"{sshpass_path} -p {password} ssh root@{ip} '{command}'"
#     print(f"Running command on {ip}: {command}")
#     result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
#     if result.returncode != 0:
#         print(f"Error executing command on {ip}: {result.stderr}")
#         sys.exit(1)
#     print(result.stdout)


# Function to install Couchbase Server
def install_couchbase_server(version, build, ips):
    for ip in ips:
        try:
            fix_hostname(ip)
            download_url = get_download_url(version, build)
            print(f"Download URL: {download_url}")
            
            # Commands to run on remote machine
            download_command = f"wget -q {download_url} -O /tmp/couchbase-server.deb  && echo 'Done'"
            fix_dependencies = "sudo apt-get install -f"
            install_command = "sudo dpkg -i /tmp/couchbase-server.deb"
            check_process_command = "ps aux | grep couchbase"
            start_service_command = "sudo systemctl start couchbase-server"
            check_service_command = "curl -s http://localhost:8091"

            # Run commands on remote server
            # if await ensure_sshpass(ip):
            run_remote_command(ip, download_command)
            run_remote_command(ip, fix_dependencies)
            run_remote_command(ip, install_command)

            # Check if Couchbase is running
            result = run_remote_command(ip, check_process_command)
            if result is None or "couchbase" not in result:
                print(f"Couchbase not found as a process on {ip}, starting the service...")
                run_remote_command(ip, start_service_command)

            time.sleep(15)

            # Check if Couchbase UI is accessible
            result = run_remote_command(ip, check_service_command)
            if result:
                print(f"Couchbase successfully installed and running on {ip}")
            else:
                print(f"Failed to access Couchbase UI on {ip}.")
            
            # # Check if Couchbase is running
            # result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} '{check_process_command}'", shell=True, capture_output=True, text=True)
            # if "couchbase" not in result.stdout:
            #     print(f"Couchbase not found as a process on {ip}, starting the service...")
            #     run_remote_command(ip, start_service_command)

            # time.sleep(15)
            
            # # Check if Couchbase UI is accessible
            # result = subprocess.run(f"sshpass -p couchbase ssh root@{ip} '{check_service_command}'", shell=True, capture_output=True, text=True)
            # if result.returncode == 0:
            #     print(f"Couchbase successfully installed and running on {ip}")
            # else:
            #     print(f"Failed to access Couchbase UI on {ip}.")
        except Exception as e:
            print(f"Error on {ip}: {e}")


# Parse command line arguments using optparse
def parse_args():
    parser = OptionParser(usage="usage: python install_couchbase.py --config <config_file> [options]")
    parser.add_option("-c", "--config", dest="config", help="Path to the JSON config file", metavar="FILE")
    parser.add_option("-v", "--version", dest="version", default=DEFAULT_VERSION,
                      help="Couchbase version to install (e.g., 7.6.2)")
    parser.add_option("-b", "--build", dest="build", default=DEFAULT_BUILD,
                      help="Build number (optional). If not provided, the latest build will be used.")
    (options, args) = parser.parse_args()
    return options


# Load IPs from configuration file
def load_ips_from_config(config_path):
    with open(config_path, 'r') as file:
        config = json.load(file)
    return [server["hostname"] for server in config.get("couchbase-servers", [])]


def main():
    options = parse_args()

    # Load IPs from config file
    ips = load_ips_from_config(options.config)
    
    # Install Couchbase Server
    if options.version:
        install_couchbase_server(options.version, options.build, ips)
    else:
        install_couchbase_server("7.6.2", "3721", ips)

if __name__ == "__main__":
    main()