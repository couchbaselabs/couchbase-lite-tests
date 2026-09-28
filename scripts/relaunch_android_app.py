#!/usr/bin/env python3
"""Re-launch the React Native Android test server on the emulator."""

import os
import subprocess
from pathlib import Path

_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
ADB = str(Path(_sdk) / "platform-tools" / "adb") if _sdk else "adb"
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
