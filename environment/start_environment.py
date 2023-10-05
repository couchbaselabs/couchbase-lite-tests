#!/usr/bin/env python3

import sys, time
import subprocess
from json import loads

def start_environment():
    print("Bringing up docker compose...")
    subprocess.run(["docker", "compose", "up", "-d"])
    print()

    sg_count = 0
    output = subprocess.check_output(["docker", "compose", "ps", "--format", "json"]).decode().splitlines()
    for line in output:
        json = loads(line)
        if "cbl-test-sg" in json["Name"]:
            sg_count += 1
            print(f"Found SG #{sg_count}: {json['Name']}")

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

        output = subprocess.check_output(["docker", "compose", "logs"]).decode().splitlines()
        for line in output:
            if "Sync Gateway is up" in line:
                which = line.split()[0]
                if not which in seen:
                    seen.add(which)
                    sg_count -= 1
                    print("")   
                    print(f"\tSG {which} is ready!")
                    found = True

    print("")
    print("Done!")

if __name__ == "__main__":
    start_environment()

