import json
import logging
import paramiko
import subprocess
import sys
import time
import couchbase.subdocument as SD
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterTimeoutOptions, ClusterOptions
from datetime import timedelta
from optparse import OptionParser


SERVER_IP = "172.23.104.162"
USERNAME = 'Administrator'
PASSWORD = 'esabhcuoc'
BUCKET_NAME = "QE-mobile-pool"
SSH_NUM_RETRIES = 3
SSH_USERNAME = 'root'
SSH_PASSWORD = 'couchbase'
SSH_POLL_INTERVAL = 20
MOBILE_OS = ["android", "ios"]


timeout_options = ClusterTimeoutOptions(kv_timeout=timedelta(seconds=5), query_timeout=timedelta(seconds=10))
options = ClusterOptions(PasswordAuthenticator(USERNAME, PASSWORD), timeout_options=timeout_options)
cluster = Cluster('couchbase://{}'.format(SERVER_IP), options)
cb = cluster.bucket(BUCKET_NAME)
cb_coll = cb.default_collection()


def log_info(message, is_verify=False):
    # pytest will capture stdout / stderr
    # by using 'print' the html reporting and running the test with -s will pick up this output in the console
    # If verify is true, the message will have the format "  > This is some message" for cleaner output

    if is_verify:
        message = "  > {}".format(message)
    try:
        print(str(message))
    except UnicodeEncodeError:
        print(str(message).encode())
    logging.info(message)


def get_nodes_available_from_mobile_pool(opts):
    """Get number of nodes available."""
    log_info(f"Getting count of node(s) with OS: {opts.nodes_os_type}, Version: {opts.nodes_os_version}")

    query = query_results(opts)
    count = 0
    for row in query:
        doc_id = row["id"]
        if opts.nodes_os_type in MOBILE_OS:
            check_alive = check_device_alive(doc_id)
        else:
            check_alive = check_vm_alive(doc_id)
        if check_alive:
            count += 1
    print(count)


def reserve_nodes(opts):
    """Reserve nodes if enough are available and update the pool.json file."""
    log_info(f"Attempting to reserve {opts.num_of_nodes} node(s) with OS: {opts.nodes_os_type}, Version: {opts.nodes_os_version}")

    query = query_results(opts)
    pool_list = []

    for row in query:
        doc_id = row["id"]

        res = cb_coll.lookup_in(doc_id, (SD.get("poolId"),))

        # Check if the poolId is "edge-server"
        if res != "edge-server":
            log_info(f"Skipping node {doc_id} as poolId is not 'edge-server'")
            continue
        
        is_node_reserved = reserve_node(doc_id, opts.job_name)
        
        if opts.nodes_os_type not in MOBILE_OS:
            vm_alive = check_vm_alive(doc_id)
            if not vm_alive:
                query_str = "update `{}` set state=\"VM_NOT_ALIVE\" where meta().id='{}' " \
                    "and state='available'".format(doc_id, doc_id)
                query = cluster.query(query_str)
            if is_node_reserved and vm_alive:
                pool_list.append(str(doc_id))
        else:
            device_alive = check_device_alive(doc_id)
            if not device_alive:
                query_str = "update `{}` set state=\"device_down\" where meta().id='{}' " \
                            "and state='available'".format(doc_id, doc_id)
                query = cluster.query(query_str)
            if is_node_reserved and device_alive:
                pool_list.append(str(doc_id))
        
        if len(pool_list) == int(opts.num_of_nodes):
            return pool_list

    # Not able to allocate all the requested nodes, hence release the node back to the pool
    release_nodes(pool_list, opts.job_name)
    raise Exception("Not enough free node/s available to satisfy the request")


def query_results(opts):
    # Getting list of available nodes through n1ql query
    query_phone_in_slave = ""
    if opts.nodes_os_type in MOBILE_OS:
        if opts.slave_ip is None:
            raise Exception("\n**** we need slave ip to get phone info on that slave ***")
        opts.nodes_os_version = "7"
        query_phone_in_slave = "AND slave_ip='{}'".format(opts.slave_ip)
    query_str = "select meta().id from `{}` where os='{}' " \
                "AND os_version='{}' AND state='available' {}" \
                .format(BUCKET_NAME, opts.nodes_os_type, opts.nodes_os_version, query_phone_in_slave)
    return cluster.query(query_str)


def check_vm_alive(server):
    num_retries = 0
    while num_retries <= SSH_NUM_RETRIES:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=server, username=SSH_USERNAME, password=SSH_PASSWORD)
            print("Successfully established test ssh connection to {0}. VM is recognized as valid.".format(server))
            return True
        except Exception as e:
            print("Exception occured while trying to establish ssh connection with {0}: {1}".format(server, str(e)))
            num_retries = num_retries + 1
            time.sleep(SSH_POLL_INTERVAL)
            continue


def check_device_alive(device_ip):
    command = ["ping", "-c", "1", device_ip]
    return subprocess.run(args=command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def reserve_node(doc_id, job_name, counter=0):
    """Reserve a node for a given job."""
    result = cb_coll.get(doc_id)
    doc = result.value
    curr_cas = result.cas
    # Reserving the ip from the pool and updating the entry in the bucket
    doc["prevUser"] = doc["username"]
    doc["username"] = job_name
    doc["state"] = "booked"
    doc["booked_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        cb_coll.replace(doc_id, doc, cas=curr_cas)
        return True
    except CouchbaseException as err:
        result = cb_coll.get(doc_id)
        doc = result.value
        if doc["state"] != "booked" and counter < 5:
            log_info("Attempt to reserve node {} failed due to error {}".format(doc_id, err))
            log_info("Re-try attempt no. {}".format(counter))
            return reserve_node(doc_id, job_name, counter + 1)
        else:
            log_info("Node has been booked by job {}".format(doc["username"]))
            log_info("Checking for other node")
            return False
    except Exception as err:
        log_info("Exception occurred: {}".format(err))
        return False


def release_nodes(opts):
    """Release nodes back to the pool."""
    log_info(f"Releasing nodes: {opts.pool_list} back to the pool")

    cleaned_pool_list = opts.pool_list.strip().rstrip(',')

    # If there are commas, split by commas; if there are spaces, split by spaces
    if "," in cleaned_pool_list:
        node_list = cleaned_pool_list.split(',')
    elif " " in cleaned_pool_list:
        node_list = cleaned_pool_list.split()
    else:
        node_list = [cleaned_pool_list]

    for node in node_list:
        result = cb_coll.get(str(node))
        print(result.value)
        doc = result.value
        print(doc, "Doc details")
        print("\njob name: ", opts.job_name)
        print("\ndoc username: ", doc["username"])
        if str(doc["username"] or "") == str(opts.job_name or ""):
            doc["prevUser"] = doc["username"]
            doc["username"] = ""
            doc["state"] = "available"
            cb_coll.replace(node, doc)
        else:
            log_info("Machine is reserved by other Job: {}".format(doc["username"]))
            raise Exception("Unable to release the node. Release node manually")


def main():
    usage = """usage: vm_pool_manager.py
    --num-of-nodes
    --nodes-os-type
    usage: python vm_pool_manager.py --num-of-nodes=3 --nodes-os-type=centos
    ** ** Release server back to pool
    python vm_pool_manager.py --release-nodes --pool-list 10.100.x.x,10.100.x.x
    ** ** Get number of servers available
    python vm_pool_manager.py --get-available-nodes --nodes-os-type=centos
    ** ** Reserve a device from a specific slave
    python vm_pool_manager.py --reserve-nodes --num-of-nodes=1 --nodes-os-type=android" 
    """

    parser = OptionParser(usage=usage)

    parser.add_option("--num-of-nodes",
                      action="store", dest="num_of_nodes", default=2,
                      help="Specify the number of nodes you need from the server pool. Default value is 2")

    parser.add_option("--nodes-os-type",
                      action="store", dest="nodes_os_type", default="ubuntu",
                      help="Specify the OS type of requested nodes")

    parser.add_option("--nodes-os-version",
                      action="store", dest="nodes_os_version", default="22",
                      help="Specify the OS version of requested nodes")

    parser.add_option("--slave-ip",
                      action="store", dest="slave_ip", default=None,
                      help="Use to find device attached to this slave")

    parser.add_option("--job-name",
                      action="store", dest="job_name",
                      help="Specify the job name which is requesting/releasing nodes")

    parser.add_option("--reserve-nodes",
                      action="store_true", dest="reserve_nodes", default=False,
                      help="Use this parameter to request to reserve nodes")

    parser.add_option("--get-available-nodes",
                      action="store_true", dest="get_available_nodes", default=False,
                      help="Use this parameter to get available nodes")

    parser.add_option("--release-nodes",
                      action="store_true", dest="release_nodes", default=False,
                      help="Use this parameter to request to release nodes")

    parser.add_option("--pool-list",
                      action="store", dest="pool_list",
                      help="Pass the list of IPs to be released back to the pool.")

    arg_parameters = sys.argv[1:]

    # Parse arguments
    (opts, args) = parser.parse_args(arg_parameters)

    mutually_exclusive_options = [
        opts.reserve_nodes,
        opts.get_available_nodes,
        opts.release_nodes
    ]

    # Ensure only one action is selected
    if sum(bool(opt) for opt in mutually_exclusive_options) > 1:
        raise Exception("You can only specify one of --reserve-nodes, --get-available-nodes, or --release-nodes.")
    elif opts.reserve_nodes:
        node_list = reserve_nodes(opts)
        log_info("Nodes reserved: {}".format(node_list))
        if opts.nodes_os_type not in MOBILE_OS:
            with open("resources/pool.json", "w") as fh:
                pool_json_str = '{ "ips": ['
                for node in node_list:
                    pool_json_str += '"{}", '.format(node)
                pool_json_str = pool_json_str.rstrip(', ')
                pool_json_str += "]"
                pool_json_str += "}"
                fh.write(pool_json_str)
    elif opts.release_nodes:
        if opts.pool_list:
            release_nodes(opts)
        else:
            raise AttributeError("You must provide a list of IPs to release.")
    elif opts.get_available_nodes:
        get_nodes_available_from_mobile_pool(opts)
    else:
        raise Exception("You must specify at least one of --reserve-nodes, --get-available-nodes, or --release-nodes.")

if __name__ == "__main__":
    main()

