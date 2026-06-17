#!/usr/bin/env python3
"""Re-launch the React Native iOS test server on the simulator."""

import subprocess
import sys

SIM = "793881A3-248F-4AB1-A26B-6D581917BF0E"
BUNDLE = "com.cbltestserver"
WS_URL = "ws://127.0.0.1:8765"


def main() -> None:
    print(f"[relaunch_ios] simulator={SIM} wsURL={WS_URL}", flush=True)
    subprocess.run(["xcrun", "simctl", "terminate", SIM, BUNDLE], check=False)
    subprocess.run(
        [
            "xcrun",
            "simctl",
            "launch",
            SIM,
            BUNDLE,
            "-deviceID",
            "ws0",
            "-wsURL",
            WS_URL,
        ],
        check=True,
    )
    print("[relaunch_ios] Done", flush=True)


if __name__ == "__main__":
    main()
