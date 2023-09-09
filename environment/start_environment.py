#!/usr/bin/env python3

import subprocess
import time
from json import loads

def start_environment():
    print("Bringing up docker compose...")
    subprocess.run(["docker", "compose", "up", "-d"])
    print()
    ps_output = loads(subprocess.check_output(["docker", "compose", "ps", "--format", "json"]).decode())
    sg_count = 0
    for entry in ps_output:
        if "cbl-test-sg" in entry["Name"]:
            sg_count += 1
            print(f"Found SG #{sg_count}: {entry['Name']}")

    retry = True
    seen = set()
    while retry:
        ready_sg = 0
        print("\tWaiting for environment...")
        output = subprocess.check_output(["docker", "compose", "logs"]).decode().splitlines()
        for line in output:
            if "Sync Gateway is up" in line:
                ready_sg += 1
                retry = ready_sg != sg_count
                which = line.split()[0]
                if not which in seen:
                    seen.add(which)
                    print(f"\t{which} ready!")
                break

        if retry:
            time.sleep(2)
        
    print("Done!")

if __name__ == "__main__":
    start_environment()