#!/usr/bin/env python3
"""Re-launch the React Native iOS test server on the simulator."""

import subprocess

BUNDLE = "com.cbltestserver"
WS_URL = "ws://127.0.0.1:8765"


def main() -> None:
    print(f"[relaunch_ios] simulator=booted wsURL={WS_URL}", flush=True)
    subprocess.run(["xcrun", "simctl", "terminate", "booted", BUNDLE], check=False)
    subprocess.run(
        [
            "xcrun",
            "simctl",
            "launch",
            "booted",
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
