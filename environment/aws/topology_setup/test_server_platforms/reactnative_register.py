import platform
import shutil
import subprocess
from pathlib import Path

import click

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import (
    DOWNLOADED_TEST_SERVER_DIR,
    TEST_SERVER_DIR,
    TestServer,
)
from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

RN_TEST_SERVER_DIR = TEST_SERVER_DIR / "reactnative"
ZIP_FOLDER_NAME = "compressed"
ZIP_DIR = RN_TEST_SERVER_DIR / ZIP_FOLDER_NAME

WS_PORT = 8765
APP_BUNDLE_ID = "com.cbltestserver"
DEVICE_ID = "ws0"



def _find_adb() -> Path:
    """Locate the adb binary."""
    find_command = "where" if platform.system() == "Windows" else "which"
    result = subprocess.run(
        [find_command, "adb"], check=False, capture_output=True, text=True
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())

    potential_locations = [
        "/opt/homebrew/share/android-commandlinetools/platform-tools/",
        "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools",
    ]
    for loc in potential_locations:
        for suffix in ["adb", "adb.exe"]:
            p = Path(loc) / suffix
            if p.exists():
                return p

    raise RuntimeError("adb not found")


def _get_host_ip_for_android(adb: Path, location: str) -> str:
    """Determine the host IP reachable from an Android device.

    For emulators the host loopback is 10.0.2.2.  For physical USB devices
    we pick the first non-loopback IPv4 address on the host machine.
    """
    result = subprocess.run(
        [str(adb), "-s", location, "shell", "getprop", "ro.hardware"],
        check=False,
        capture_output=True,
        text=True,
    )
    hw = result.stdout.strip().lower()
    if "goldfish" in hw or "ranchu" in hw:
        return "10.0.2.2"

    import netifaces

    for iface in netifaces.interfaces():
        if iface == "lo" or iface.startswith("lo"):
            continue
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            ip = addrs[netifaces.AF_INET][0].get("addr", "")
            if ip and not ip.startswith("169.254") and not ip.startswith("127."):
                return ip

    raise RuntimeError("Cannot determine host IP reachable from Android device")


def _get_host_ip_for_ios() -> str:
    """Determine the host IP reachable from an iOS device.

    For simulators we return localhost.  For physical devices we pick the
    first non-loopback IPv4 address.
    """
    import netifaces

    for iface in netifaces.interfaces():
        if iface == "lo" or iface.startswith("lo"):
            continue
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            ip = addrs[netifaces.AF_INET][0].get("addr", "")
            if ip and not ip.startswith("169.254") and not ip.startswith("127."):
                return ip

    raise RuntimeError("Cannot determine host IP reachable from iOS device")


# ---------------------------------------------------------------------------
# Android Bridge
# ---------------------------------------------------------------------------


class ReactNativeAndroidBridge(PlatformBridge):
    def __init__(self, apk_path: str):
        self.__apk_path = apk_path
        self.__adb = _find_adb()

    def validate(self, location: str) -> None:
        result = subprocess.run(
            [str(self.__adb), "-s", location, "get-state"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Android device {location} not found!")

    def install(self, location: str) -> None:
        header(f"Installing React Native APK to {location}")
        subprocess.run(
            [str(self.__adb), "-s", location, "install", "-r", self.__apk_path],
            check=True,
            capture_output=False,
        )

    def run(self, location: str) -> None:
        header(f"Launching React Native app on {location}")
        subprocess.run(
            [str(self.__adb), "-s", location, "shell", "am", "force-stop", APP_BUNDLE_ID],
            check=False,
            capture_output=True,
        )

        host_ip = _get_host_ip_for_android(self.__adb, location)
        ws_url = f"ws://{host_ip}:{WS_PORT}"
        click.echo(f"Auto-connect URL: {ws_url}  deviceID: {DEVICE_ID}")

        subprocess.run(
            [
                str(self.__adb), "-s", location, "shell", "am", "start",
                "-n", f"{APP_BUNDLE_ID}/.MainActivity",
                "--es", "deviceID", DEVICE_ID,
                "--es", "wsURL", ws_url,
            ],
            check=True,
            capture_output=False,
        )

    def stop(self, location: str) -> None:
        header(f"Stopping React Native app on {location}")
        subprocess.run(
            [str(self.__adb), "-s", location, "shell", "am", "force-stop", APP_BUNDLE_ID],
            check=True,
            capture_output=False,
        )

    def uninstall(self, location: str) -> None:
        header(f"Uninstalling React Native app from {location}")
        subprocess.run(
            [str(self.__adb), "-s", location, "uninstall", APP_BUNDLE_ID],
            check=False,
            capture_output=False,
        )

    def _get_ip(self, location: str) -> str | None:
        result = subprocess.run(
            [
                str(self.__adb), "-s", location, "shell",
                "ip", "-f", "inet", "addr", "show", "wlan0",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "inet" in line:
                return line.strip().split(" ")[1].split("/")[0]
        return None


# ---------------------------------------------------------------------------
# iOS Bridge
# ---------------------------------------------------------------------------


class ReactNativeIOSBridge(PlatformBridge):
    def __init__(self, app_path: str):
        self.__app_path = app_path

    def validate(self, location: str) -> None:
        result = subprocess.run(
            [
                "xcrun", "devicectl", "device", "info", "details",
                "--device", location,
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"iOS device {location} not found via devicectl!")

    def install(self, location: str) -> None:
        header(f"Installing React Native app to iOS device {location}")
        subprocess.run(
            [
                "xcrun", "devicectl", "device", "install", "app",
                "--device", location,
                self.__app_path,
            ],
            check=True,
            capture_output=False,
        )

    def run(self, location: str) -> None:
        header(f"Launching React Native app on iOS device {location}")
        subprocess.run(
            [
                "xcrun", "devicectl", "device", "process", "terminate",
                "--device", location,
                "--pid", "0",
            ],
            check=False,
            capture_output=True,
        )

        host_ip = _get_host_ip_for_ios()
        ws_url = f"ws://{host_ip}:{WS_PORT}"
        click.echo(f"Auto-connect URL: {ws_url}  deviceID: {DEVICE_ID}")

        result = subprocess.run(
            [
                "xcrun", "devicectl", "device", "process", "launch",
                "--device", location,
                APP_BUNDLE_ID,
                "--", "-deviceID", DEVICE_ID, "-wsURL", ws_url,
            ],
            check=True,
            capture_output=True,
        )
        click.echo(result.stdout.decode("utf-8", errors="replace"))

    def stop(self, location: str) -> None:
        header(f"Stopping React Native app on iOS device {location}")
        try:
            result = subprocess.run(
                [
                    "xcrun", "devicectl", "device", "info", "apps",
                    "--device", location,
                    "--bundle-id", APP_BUNDLE_ID,
                    "--hide-headers", "--hide-default-columns",
                    "--columns", "path",
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            click.secho("App not found on device; skipping termination.", fg="yellow")
            return

        stdout = result.stdout.decode("utf-8").splitlines()
        if not stdout:
            click.secho("App not in device list; skipping termination.", fg="yellow")
            return

        app_path = stdout[-1].strip()
        try:
            result = subprocess.run(
                [
                    "xcrun", "devicectl", "device", "info", "processes",
                    "--device", location,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            click.secho("Failed to list processes; skipping termination.", fg="yellow")
            return

        proc_lines = result.stdout.decode("utf-8").splitlines()
        pid_line = next((l for l in proc_lines if app_path in l), None)
        if not pid_line:
            click.echo("App process not running.")
            return

        pid = pid_line.split(" ")[0]
        click.echo(f"Terminating PID {pid}")
        subprocess.run(
            [
                "xcrun", "devicectl", "device", "process", "terminate",
                "--device", location, "--pid", pid,
            ],
            check=False,
            capture_output=True,
        )

    def uninstall(self, location: str) -> None:
        click.echo("iOS app uninstall deliberately not implemented")

    def _get_ip(self, location: str) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Test Server classes
# ---------------------------------------------------------------------------


class _ReactNativeTestServerBase(TestServer):
    """Shared logic for React Native test servers on both platforms."""

    def __init__(self, version: str):
        super().__init__(version)

    @property
    def product(self) -> str:
        return "cbl-reactnative"

    def _working_dir(self) -> Path:
        if self._downloaded:
            return DOWNLOADED_TEST_SERVER_DIR / "reactnative" / self.version
        return RN_TEST_SERVER_DIR


@TestServer.register("reactnative_android")
class ReactNativeAndroidTestServer(_ReactNativeTestServerBase):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "reactnative_android"

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_android.apk"

    def build(self) -> None:
        header(f"Building React Native Android test server {self.version}")
        working = self._working_dir()
        subprocess.run(["npm", "install"], check=True, cwd=working)
        subprocess.run(
            ["./gradlew", "assembleRelease"],
            check=True,
            cwd=working / "android",
        )

    def compress_package(self):
        header(f"Compressing React Native Android test server")
        apk_path = (
            RN_TEST_SERVER_DIR / "android" / "app" / "build"
            / "outputs" / "apk" / "release" / "app-release.apk"
        )
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        dest = ZIP_DIR / "testserver_android.apk"
        shutil.copy(apk_path, dest)
        return str(dest)

    def uncompress_package(self, path):
        click.secho("No uncompressing needed for Android APK", fg="yellow")

    def create_bridge(self, **kwargs):
        if self._downloaded:
            apk_path = (
                DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version
                / "testserver_android.apk"
            )
        else:
            apk_path = (
                RN_TEST_SERVER_DIR / "android" / "app" / "build"
                / "outputs" / "apk" / "release" / "app-release.apk"
            )
        return ReactNativeAndroidBridge(str(apk_path))


@TestServer.register("reactnative_ios")
class ReactNativeIOSTestServer(_ReactNativeTestServerBase):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "reactnative_ios"

    @property
    def latestbuilds_path(self) -> str:
        version_parts = self.version.split("-")
        return f"{self.product}/{version_parts[0]}/{version_parts[1]}/testserver_ios.zip"

    def build(self) -> None:
        header(f"Building React Native iOS test server {self.version}")
        working = self._working_dir()
        subprocess.run(["npm", "install"], check=True, cwd=working)
        # Run pod install via a login shell so macOS profile scripts (Homebrew,
        # rbenv, rvm, etc.) are sourced and the pod binary is on PATH regardless
        # of how CocoaPods was installed or what PATH Jenkins inherited.
        # Use zsh (macOS default since Catalina); fall back to bash so the
        # PATH setup in ~/.zprofile / ~/.zshrc is respected.
        zsh = shutil.which("zsh") or "/bin/zsh"
        subprocess.run(
            [zsh, "-lc", "pod install"],
            check=True,
            cwd=working / "ios",
        )
        subprocess.run(
            [
                "xcodebuild",
                "-workspace", "CblTestServer.xcworkspace",
                "-scheme", "CblTestServer",
                "-sdk", "iphoneos",
                "-configuration", "Release",
                "-derivedDataPath", str(working / "ios" / "build"),
                "-allowProvisioningUpdates",
            ],
            check=True,
            cwd=working / "ios",
        )

    def compress_package(self):
        header(f"Compressing React Native iOS test server")
        app_dir = (
            RN_TEST_SERVER_DIR / "ios" / "build" / "Build" / "Products"
            / "Release-iphoneos" / "CblTestServer.app"
        )
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = ZIP_DIR / "testserver_ios.zip"
        zip_directory(app_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path):
        unzip_directory(path, path.parent / "CblTestServer.app")
        path.unlink()

    def create_bridge(self, **kwargs):
        if self._downloaded:
            app_path = (
                DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version
                / "CblTestServer.app"
            )
        else:
            app_path = (
                RN_TEST_SERVER_DIR / "ios" / "build" / "Build" / "Products"
                / "Release-iphoneos" / "CblTestServer.app"
            )
        return ReactNativeIOSBridge(str(app_path))


# Keep the legacy "reactnative" registration so existing topology files
# that use the unsplit platform name still work.  It delegates to the
# Android variant by default.
@TestServer.register("reactnative")
class ReactNativeLegacyTestServer(ReactNativeAndroidTestServer):
    def __init__(self, version: str):
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "reactnative"
