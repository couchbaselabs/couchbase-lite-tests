import asyncio
from cbltest import CBLPyTest
from argparse import ArgumentParser

# This is how you can get all necessary requests from
# a given API version
from cbltest.v1.requests import *
from cbltest.requests import TestServerRequestType
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorActivityLevel
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
    payload.add_dataset("travel-sample", ["db1"])

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
    payload = PostGetAllDocumentIDsRequestBody("db1", "inventory.airlines")
    request = rf.create_request(TestServerRequestType.ALL_DOC_IDS, payload)
    resp = await rf.send_request(0, request)

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
    sg_payload = PutDatabasePayload("db")
    sg_payload.add_collection()
    sg_payload.enable_guest()
    await cloud.put_empty_database("db", sg_payload, "db")

    dbs = await tester.test_servers[0].create_and_reset_db("travel-sample", ["db1"])
    db = dbs[0]

    async with db.batch_updater() as b:
        b.delete_document("inventory.airlines", "airline_85")

    # all_docs = await db.get_all_documents("inventory.airlines")
    # print(f"{len(all_docs.collections[0].document_ids)} documents found")

    replicator = Replicator(db, "ws://localhost:4984/db", replicator_type=ReplicatorType.PUSH, collections=[
        ReplicatorCollectionEntry("inventory.airlines")
    ])

    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    print(f"{status.progress.document_count} documents completed")
    if status.error is not None:
        print(status.error.message)

if __name__ == "__main__":
    #asyncio.run(cli_main())
    asyncio.run(api())
