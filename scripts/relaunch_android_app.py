#!/usr/bin/env python3
"""Re-launch the React Native Android test server on the emulator."""

import subprocess
import sys

ADB = "adb"
SERIAL = "emulator-5554"
PACKAGE = "com.cbltestserver"
ACTIVITY = "com.cbltestserver/.MainActivity"
WS_URL = "ws://127.0.0.1:8765"


def main() -> None:
    print(f"[relaunch_android] device={SERIAL} wsURL={WS_URL}", flush=True)
    subprocess.run(
        [ADB, "-s", SERIAL, "shell", "am", "force-stop", PACKAGE],
        check=False,
    )
    subprocess.run(
        [
            ADB,
            "-s",
            SERIAL,
            "shell",
            "am",
            "start",
            "-n",
            ACTIVITY,
            "--es",
            "deviceID",
            "ws0",
            "--es",
            "wsURL",
            WS_URL,
        ],
        check=True,
    )
    print("[relaunch_android] Done", flush=True)


if __name__ == "__main__":
    main()
