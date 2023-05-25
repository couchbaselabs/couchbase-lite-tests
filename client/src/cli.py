from cbltest import CBLPyTest
from argparse import ArgumentParser

from cbltest.requests import RequestFactory
from cbltest.v1.requests import PostResetRequestBody

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
    print(tester)

    rf = RequestFactory(2)
    payload = PostResetRequestBody()
    payload.add_dataset("catalog", ["db1", "db2"])
    request = rf.create_post_reset(payload)
    print(request)
    resp = request.send("http://www.google.com")
    


if __name__ == "__main__":
    cli_main()
