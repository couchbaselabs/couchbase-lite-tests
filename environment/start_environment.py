#!/usr/bin/env python3

import subprocess
import sys
import time
from json import loads


def start_environment():
    print("Bringing up docker compose...")
    subprocess.run(["docker", "compose", "build"])
    subprocess.run(
        [
            "docker",
            "compose",
            "up",
            "-d",
        ]
    )
    print()

    sg_count = 0
    output = (
        subprocess.check_output(["docker", "compose", "ps", "--format", "json"])
        .decode()
        .splitlines()
    )
    # Docker compose v2.21+ changes to return a seprate JSON dict per line for each process instead of
    # a single array of all processes in one line. To support new and old version of docker compose,
    # read JSON object line-by-line and wrap the JSON dict in an array to consolidate the logic detecting
    # cbl-test-sg processes.
    for line in output:
        json = loads(line)
        processes = []
        if isinstance(json, list):
            processes = json
        else:
            processes.append(json)

        for process in processes:
            if "cbl-test-sg" in process["Name"]:
                sg_count += 1
                print(f"Found SG #{sg_count}: {process['Name']}")

    found = True
    seen = set()
    while sg_count > 0:
        if found:
            print(f"\tWaiting for {sg_count} SGs..", end="")
            found = False
        else:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(2)

        output = (
            subprocess.check_output(["docker", "compose", "logs"]).decode().splitlines()
        )
        for line in output:
            if "Sync Gateway is up" in line:
                which = line.split()[0]
                if which not in seen:
                    seen.add(which)
                    sg_count -= 1
                    print("")
                    print(f"\tSG {which} is ready!")
                    found = True

    print("")
    print("Done!")


if __name__ == "__main__":
    start_environment()
