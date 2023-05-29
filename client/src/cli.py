from cbltest import CBLPyTest
from argparse import ArgumentParser

from cbltest.requests import RequestFactory
from cbltest.v1.requests import *

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
    tester = CBLPyTest(args.config, args.log_level, args.test_props, args.output)

    rf = RequestFactory(tester.config.test_servers[0])
    payload = PostResetRequestBody()
    payload.add_dataset("travel-sample", ["db1"])
    request = rf.create_post_reset(payload)
    resp = rf.send_request(request)
    
    db_update = DatabaseUpdateEntry(DatabaseUpdateType.DELETE, "inventory.airlines", "airline_85")
    payload = PostUpdateDatabaseRequestBody("db1", [db_update])
    request = rf.create_post_update_database(payload)
    resp = rf.send_request(request)

    payload = PostGetAllDocumentIDsRequestBody("db1")
    payload.collections.extend(["inventory.airlines"])
    request = rf.create_post_get_all_document_ids(payload)
    resp = rf.send_request(request)

if __name__ == "__main__":
    cli_main()