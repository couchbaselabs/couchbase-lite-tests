import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import click

from environment.aws.common.io import unzip_directory, zip_directory
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import (
    DOWNLOADED_TEST_SERVER_DIR,
    TEST_SERVER_DIR,
    TestServer,
)
from environment.aws.topology_setup.test_server_platforms.android_bridge import AndroidBridge
from environment.aws.topology_setup.test_server_platforms.platform_bridge import (
    PlatformBridge,
)

RN_TEST_SERVER_DIR = TEST_SERVER_DIR / "reactnative"
ZIP_FOLDER_NAME = "compressed"
ZIP_DIR = RN_TEST_SERVER_DIR / ZIP_FOLDER_NAME

# The test server app connects back to the pytest WebSocket router on this port.
WS_PORT = 8765
APP_BUNDLE_ID = "com.cbltestserver"


def _get_host_ip_for_ios() -> str:
    """Determine the host IP that a physical iOS device can reach: the first
    non-loopback, non-link-local IPv4 address of this machine."""
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
# iOS Bridge
# ---------------------------------------------------------------------------


class ReactNativeIOSBridge(PlatformBridge):
    def __init__(self, app_path: str, device_id: str | None) -> None:
        self.__app_path = app_path
        self.__device_id = device_id

    def validate(self, location: str) -> None:
        result = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "info",
                "details",
                "--device",
                location,
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
                "xcrun",
                "devicectl",
                "device",
                "install",
                "app",
                "--device",
                location,
                self.__app_path,
            ],
            check=True,
            capture_output=False,
        )

    def run(self, location: str) -> None:
        if self.__device_id is None:
            raise RuntimeError("A WebSocket device ID is required to launch the React Native test server")

        # Stop any instance left over from a previous launch so the new launch
        # starts fresh and connects back with the arguments below.
        self.stop(location)

        header(f"Launching React Native app on iOS device {location}")
        host_ip = _get_host_ip_for_ios()
        ws_url = f"ws://{host_ip}:{WS_PORT}"
        click.echo(f"Auto-connect URL: {ws_url}  deviceID: {self.__device_id}")

        result = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "process",
                "launch",
                "--device",
                location,
                APP_BUNDLE_ID,
                "--",
                "-deviceID",
                self.__device_id,
                "-wsURL",
                ws_url,
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
                    "xcrun",
                    "devicectl",
                    "device",
                    "info",
                    "apps",
                    "--device",
                    location,
                    "--bundle-id",
                    APP_BUNDLE_ID,
                    "--hide-headers",
                    "--hide-default-columns",
                    "--columns",
                    "path",
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
                    "xcrun",
                    "devicectl",
                    "device",
                    "info",
                    "processes",
                    "--device",
                    location,
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
                "xcrun",
                "devicectl",
                "device",
                "process",
                "terminate",
                "--device",
                location,
                "--pid",
                pid,
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

    def __init__(self, version: str) -> None:
        super().__init__(version)

    @property
    def product(self) -> str:
        return "couchbase-lite-react-native"

    def _working_dir(self) -> Path:
        if self._downloaded:
            return DOWNLOADED_TEST_SERVER_DIR / "reactnative" / self.version
        return RN_TEST_SERVER_DIR

    def _prepare_npm(self) -> None:
        """Pin the cbl-reactnative dependency to the ProGet build for this version.

        package.json ships with a default version of @couchbase/couchbase-lite-react-native.
        This method overwrites that entry with the exact build version
        (e.g. 1.1.1-3) so that ``npm install`` fetches the correct artifact
        from the ProGet cbl-npm feed.
        """
        pkg_path = self._working_dir() / "package.json"
        with open(pkg_path) as f:
            pkg = json.load(f)
        pkg["dependencies"]["cbl-reactnative"] = f"npm:@couchbase/couchbase-lite-react-native@{self.version}"
        with open(pkg_path, "w") as f:
            json.dump(pkg, f, indent=2)
            f.write("\n")


@TestServer.register("reactnative_android")
class ReactNativeAndroidTestServer(_ReactNativeTestServerBase):
    def __init__(self, version: str) -> None:
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "reactnative_android"

    @property
    def latestbuilds_path(self) -> str:
        return self.artifact_path("testserver_android.apk")

    def build(self) -> None:
        header(f"Building React Native Android test server {self.version}")
        working = self._working_dir()
        self._prepare_npm()
        subprocess.run(["npm", "install"], check=True, cwd=working)
        subprocess.run(["npm", "run", "bundle-datasets"], check=True, cwd=working)
        subprocess.run(
            ["./gradlew", "assembleRelease"],
            check=True,
            cwd=working / "android",
        )

    def compress_package(self) -> str:
        header("Compressing React Native Android test server")
        apk_path = RN_TEST_SERVER_DIR / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        dest = ZIP_DIR / "testserver_android.apk"
        shutil.copy(apk_path, dest)
        return str(dest)

    def uncompress_package(self, path: Path) -> None:
        click.secho("No uncompressing needed for Android APK", fg="yellow")

    def create_bridge(self, **kwargs: Any) -> PlatformBridge:
        if self._downloaded:
            apk_path = DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version / "testserver_android.apk"
        else:
            apk_path = (
                RN_TEST_SERVER_DIR / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
            )
        # The app connects back to the pytest WebSocket router through an adb reverse
        # tunnel, so it reaches the host on 127.0.0.1 regardless of the device's network.
        device_id = kwargs.get("device_id")
        launch_extras = {"deviceID": device_id, "wsURL": f"ws://127.0.0.1:{WS_PORT}"} if device_id else None
        return AndroidBridge(
            str(apk_path),
            APP_BUNDLE_ID,
            needs_permissions=False,
            launch_extras=launch_extras,
            reverse_ports=[WS_PORT],
            restart_on_run=True,
        )


@TestServer.register("reactnative_ios")
class ReactNativeIOSTestServer(_ReactNativeTestServerBase):
    def __init__(self, version: str) -> None:
        super().__init__(version)

    @property
    def platform(self) -> str:
        return "reactnative_ios"

    @property
    def latestbuilds_path(self) -> str:
        return self.artifact_path("testserver_ios.zip")

    @staticmethod
    def _ensure_cocoapods() -> str:
        """Return a path to the `pod` executable, installing CocoaPods if needed.

        Strategy (in order):
        1. Already on PATH — nothing to do.
        2. Homebrew is available — `brew install cocoapods` (pre-built bottle,
           fast, no permission issues).
        3. Fall back to `gem install` with a user-writable GEM_HOME so the
           system Ruby gem directory (/Library/Ruby/Gems) is never touched.
        """
        pod = shutil.which("pod")
        if pod:
            return pod

        # Homebrew (standard on Apple Silicon Macs, lives at /opt/homebrew)
        brew = shutil.which("brew") or "/opt/homebrew/bin/brew"
        if Path(brew).exists():
            subprocess.run([brew, "install", "cocoapods"], check=True)
            pod = shutil.which("pod") or "/opt/homebrew/bin/pod"
            if Path(pod).exists():
                return pod

        # Last resort: install into a user-writable GEM_HOME so no sudo is needed
        gem_home = Path.home() / ".local" / "share" / "gem"
        gem_bin = gem_home / "bin"
        gem_home.mkdir(parents=True, exist_ok=True)
        gem_env = {
            **os.environ,
            "GEM_HOME": str(gem_home),
            "PATH": f"{gem_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        subprocess.run(
            ["gem", "install", "cocoapods", "--version", "~> 1.16.2", "--no-document"],
            check=True,
            env=gem_env,
        )
        return str(gem_bin / "pod")

    @staticmethod
    def _resolve_node_binary() -> str:
        """Find the node binary, using npm's location as a reliable fallback.

        On CI machines node is often installed via nvm or Homebrew and is not
        on the default PATH. npm and node always live in the same bin directory,
        so if npm was found (npm install succeeded) node is there too.
        """
        node = shutil.which("node")
        if node:
            return node

        # npm and node share the same bin dir (nvm, Homebrew, etc.)
        npm = shutil.which("npm")
        if npm:
            candidate = Path(npm).parent / "node"
            if candidate.exists():
                return str(candidate)

        # nvm-managed installations
        nvm_dir = Path.home() / ".nvm" / "versions" / "node"
        if nvm_dir.is_dir():
            matches = sorted(nvm_dir.glob("*/bin/node"), reverse=True)
            if matches:
                return str(matches[0])

        # Homebrew fixed locations
        for fixed in [Path("/opt/homebrew/bin/node"), Path("/usr/local/bin/node")]:
            if fixed.exists():
                return str(fixed)

        raise RuntimeError("node binary not found; ensure Node.js >= 18 is installed")

    def build(self) -> None:
        header(f"Building React Native iOS test server {self.version}")
        working = self._working_dir()
        self._prepare_npm()
        subprocess.run(["npm", "install"], check=True, cwd=working)
        subprocess.run(["npm", "run", "bundle-datasets"], check=True, cwd=working)

        # React Native's Xcode build phases (including the Hermes Replace
        # script) all resolve node via NODE_BINARY, which .xcode.env sets to
        # `$(command -v node)`. That fails in non-login CI shells where node
        # is not on PATH. Writing .xcode.env.local before pod install ensures
        # every subsequent phase — including pod install's node invocations —
        # uses the correct binary.
        node_binary = self._resolve_node_binary()
        xcode_env_local = working / "ios" / ".xcode.env.local"
        xcode_env_local.write_text(f"export NODE_BINARY={node_binary}\n")

        pod_cmd = self._ensure_cocoapods()
        subprocess.run([pod_cmd, "install"], check=True, cwd=working / "ios")

        # The Xcode "Bundle React Native code and images" phase expects a
        # pre-built ios/main.jsbundle. Generate it now before xcodebuild runs.
        # The generated src/datasetBundle.ts is a single multi-MB module (all
        # datasets plus base64 blobs inlined), so Metro's jest-worker blows the
        # default ~2 GB V8 old-space transforming it. Raise the heap for the
        # bundle run; NODE_OPTIONS propagates to Metro's worker children.
        rn_cli = working / "node_modules" / ".bin" / "react-native"
        bundle_env = os.environ.copy()
        bundle_env["NODE_OPTIONS"] = "--max-old-space-size=8192"
        subprocess.run(
            [
                node_binary,
                str(rn_cli),
                "bundle",
                "--platform",
                "ios",
                "--dev",
                "false",
                "--entry-file",
                "index.js",
                "--bundle-output",
                "ios/main.jsbundle",
                "--assets-dest",
                "ios",
            ],
            check=True,
            cwd=working,
            env=bundle_env,
        )

        xcode_env = os.environ.copy()
        xcode_env["LANG"] = "en_US.UTF-8"
        xcode_env["LC_ALL"] = "en_US.UTF-8"
        # Set NODE_BINARY explicitly so any build phase that reads it directly
        # (rather than via .xcode.env.local) also gets the right value.
        xcode_env["NODE_BINARY"] = node_binary
        xcode_env["PATH"] = f"{Path(node_binary).parent}{os.pathsep}{xcode_env.get('PATH', '')}"
        subprocess.run(
            [
                "xcodebuild",
                "-workspace",
                "CblTestServer.xcworkspace",
                "-scheme",
                "CblTestServer",
                "-sdk",
                "iphoneos",
                "-configuration",
                "Release",
                "-derivedDataPath",
                str(working / "ios" / "build"),
                "-allowProvisioningUpdates",
            ],
            check=True,
            cwd=working / "ios",
            env=xcode_env,
        )

    def compress_package(self) -> str:
        header("Compressing React Native iOS test server")
        app_dir = RN_TEST_SERVER_DIR / "ios" / "build" / "Build" / "Products" / "Release-iphoneos" / "CblTestServer.app"
        ZIP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = ZIP_DIR / "testserver_ios.zip"
        zip_directory(app_dir, zip_path)
        return str(zip_path)

    def uncompress_package(self, path: Path) -> None:
        unzip_directory(path, path.parent / "CblTestServer.app")
        path.unlink()

    def create_bridge(self, **kwargs: Any) -> PlatformBridge:
        if self._downloaded:
            app_path = DOWNLOADED_TEST_SERVER_DIR / self.platform / self.version / "CblTestServer.app"
        else:
            app_path = (
                RN_TEST_SERVER_DIR / "ios" / "build" / "Build" / "Products" / "Release-iphoneos" / "CblTestServer.app"
            )
        return ReactNativeIOSBridge(str(app_path), kwargs.get("device_id"))
