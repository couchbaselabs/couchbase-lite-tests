import asyncio
import os
from pathlib import Path
from cbltest import CBLPyTest
from argparse import ArgumentParser

# This is how you can get all necessary requests from
# a given API version
from cbltest.v1.requests import *
from cbltest.requests import TestServerRequestType
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorBasicAuthenticator
from cbltest.api.syncgateway import PutDatabasePayload
from cbltest.api.cloud import CouchbaseCloud

# This is an example of how to use the SDK.  It will be updated as the SDK evolves.
# Currently the low level interface is being used.  This will be replaced by a higher
# one that likely will support async functionality and look more like python

async def cli_main():
    ap = ArgumentParser(prog="cli.py", description="Drives CBLPyTest from the command line for experimentation",
                          epilog="CBLPyTest is meant to be used inside of pytest tests, not from the CLI.")
    ap.add_argument("--config", metavar="PATH", help="The path to the JSON configuration for CBLPyTest", required=True)
    ap.add_argument("--log-level", metavar="LEVEL", 
                    choices=["error", "warning", "info", "verbose", "debug"], 
                    help="The log level output for the test run",
                    default="verbose")
    ap.add_argument("--test-props", metavar="PATH", help="The path to read extra test properties from")
    ap.add_argument("--output", metavar="PATH", help="The path to write Greenboard results to")
    args = ap.parse_args()

    # Create the top level object which is the entry point for a python consumer
    tester = CBLPyTest(args.config, args.log_level, args.test_props, args.output)

    # Inside the tester is the request factory, which easily constructs and sends
    # requests, and receives their responses
    rf = tester.request_factory

    # The pattern is to create a body for the desired request
    payload = PostResetRequestBody()

    # Populate the body
    payload.add_dataset("travel-samples", ["db1"])

    # Create the request
    request = rf.create_request(TestServerRequestType.RESET, payload)

    # Send the request, and receive the response
    resp = await rf.send_request(0, request)
    
    # Same pattern again
    db_update = DatabaseUpdateEntry(DatabaseUpdateType.DELETE, "inventory.airlines", "airline_85")
    payload = PostUpdateDatabaseRequestBody("db1", [db_update])
    request = rf.create_request(TestServerRequestType.UPDATE_DB, payload)
    resp = await rf.send_request(0, request)

    # One last time
    payload = PostGetAllDocumentsRequestBody("db1", "inventory.airlines")
    request = rf.create_request(TestServerRequestType.ALL_DOC_IDS, payload)
    resp = await rf.send_request(0, request)

script_path = os.path.abspath(os.path.dirname(__file__))

async def api():
    ap = ArgumentParser(prog="cli.py", description="Drives CBLPyTest from the command line for experimentation",
                          epilog="CBLPyTest is meant to be used inside of pytest tests, not from the CLI.")
    ap.add_argument("--config", metavar="PATH", help="The path to the JSON configuration for CBLPyTest", required=True)
    ap.add_argument("--log-level", metavar="LEVEL", 
                    choices=["error", "warning", "info", "verbose", "debug"], 
                    help="The log level output for the test run",
                    default="verbose")
    ap.add_argument("--test-props", metavar="PATH", help="The path to read extra test properties from")
    ap.add_argument("--output", metavar="PATH", help="The path to write Greenboard results to")
    args = ap.parse_args()

    # Create the top level object which is the entry point for a python consumer
    tester = CBLPyTest(args.config, args.log_level, args.test_props, args.output)

    cloud = CouchbaseCloud(tester.sync_gateways[0], tester.couchbase_servers[0])
    sg_payload = PutDatabasePayload("names")
    sg_payload.add_collection()
    await cloud.put_empty_database("names", sg_payload, "names")
    await tester.sync_gateways[0].load_dataset("names", Path(script_path, "..", "..", "dataset", "names-sg.json"))
    await tester.sync_gateways[0].add_user("names", "user1", "pass", {
        "_default._default": ["*"]
    })

    dbs = await tester.test_servers[0].create_and_reset_db("travel", ["db1"])
    db = dbs[0]

    replicator = Replicator(db, tester.sync_gateways[0].replication_url("names"), replicator_type=ReplicatorType.PUSH, collections=[
        ReplicatorCollectionEntry("travel.airlines")
    ], authenticator=ReplicatorBasicAuthenticator("user1", "pass"))

    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    if status.error is not None:
        print(status.error.message)

if __name__ == "__main__":
    #asyncio.run(cli_main())
    asyncio.run(api())
