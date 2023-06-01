from cbltest import CBLPyTest
from argparse import ArgumentParser

# This is how you can get all necessary requests from
# a given API version
from cbltest.v1.requests import *

# This is an example of how to use the SDK.  It will be updated as the SDK evolves.
# Currently the low level interface is being used.  This will be replaced by a higher
# one that likely will support async functionality and look more like python

def cli_main():
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
    request = rf.create_post_reset(payload)

    # Send the request, and receive the response
    resp = rf.send_request(0, request)
    
    # Same pattern again
    db_update = DatabaseUpdateEntry(DatabaseUpdateType.DELETE, "inventory.airlines", "airline_85")
    payload = PostUpdateDatabaseRequestBody("db1", [db_update])
    request = rf.create_post_update_database(payload)
    resp = rf.send_request(0, request)

    # One last time
    payload = PostGetAllDocumentIDsRequestBody("db1")
    payload.collections.extend(["inventory.airlines"])
    request = rf.create_post_get_all_document_ids(payload)
    resp = rf.send_request(0, request)

if __name__ == "__main__":
    cli_main()