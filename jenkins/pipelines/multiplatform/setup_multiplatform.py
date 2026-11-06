#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(str(SCRIPT_DIR.parents[2]))

import click
import requests

from environment.aws.common.versions import find_missing_version
from jenkins.pipelines.shared.setup_test import resolved_version, setup_test

if __name__ == "__main__":
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class TestServerPlatform:
    """
    A test server platform: the CBL SDK (`sdk`) built for one OS or variant (`os`). Its `name` is the platform
    string the prebuild job and the topology files use, e.g. "dotnet_macos".
    """

    sdk: str
    os: str
    proget_product: str

    @property
    def name(self) -> str:
        return f"{self.sdk}_{self.os}"


# Every test server platform this pipeline can run. The Jenkinsfile's progetProduct() mirrors the products.
TEST_SERVER_PLATFORMS = {
    p.name: p
    for p in [
        TestServerPlatform("swift", "ios", "couchbase-lite-ios"),
        TestServerPlatform("jak", "android", "couchbase-lite-android"),
        TestServerPlatform("jak", "desktop", "couchbase-lite-java"),
        TestServerPlatform("jak", "webservice", "couchbase-lite-java"),
        *(TestServerPlatform("dotnet", os, "couchbase-lite-net") for os in ["macos", "windows", "ios", "android"]),
        *(
            TestServerPlatform("c", os, "couchbase-lite-c")
            for os in ["macos", "windows", "linux_x86_64", "ios", "android"]
        ),
    ]
}

# Exit code for a failed sanity check: test_multiplatform.sh passes it on and the Jenkinsfile marks the run UNSTABLE.
SANITY_CHECK_EXIT_CODE = 3

# A version as given: "4", "4.1", "4.1.0" or "4.1.0-18". An empty one means the latest release.
VERSION_PATTERN = re.compile(r"\d+(\.\d+){0,2}(-\d+)?")


@dataclass(frozen=True)
class PlatformVersion:
    """
    One "<platform>=<version>" entry of PLATFORM_VERSIONS. `position` is its 1-based place in the input. A platform
    listed more than once gives its test servers their versions in that order.
    """

    position: int
    platform: TestServerPlatform
    version: str

    def __str__(self) -> str:
        return f"#{self.position} {self.platform.name}={self.version}"


@dataclass(frozen=True)
class TopologyTestServer:
    """One entry of the topology's `test_servers`, `index` being its place in that list."""

    index: int
    platform: str
    location: str

    def __str__(self) -> str:
        return f"test_servers[{self.index}] {self.platform} at {self.location}"


class SanityCheck:
    """
    Collects every problem in the input and the topology, each labelled with where it is, so that a single run
    reports all of them before anything is set up.
    """

    def __init__(self) -> None:
        self.problems: list[str] = []

    def problem(self, source: str, message: str) -> None:
        self.problems.append(f"[{source}] {message}")
        click.secho(f"  ✗ [{source}] {message}", fg="red")

    def existing_version(
        self, source: str, label: str, resolve_product: str, lookup_product: str, version: str
    ) -> str | None:
        """
        Resolves `version` of `label` (as `resolve_product`) to a full version and checks that it exists (as
        `lookup_product`). Returns the full version, or None after recording why it can't be used.
        """
        if version and not VERSION_PATTERN.fullmatch(version):
            self.problem(source, f"{label}: '{version}' is not a version like 4, 4.1, 4.1.0 or 4.1.0-18")
            return None

        try:
            full_version = resolved_version(resolve_product, version or None)
            missing = find_missing_version(lookup_product, full_version)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                self.problem(source, f"{label}: no release of {resolve_product} matches '{version}'")
            else:
                self.problem(source, f"{label}: version lookup failed: {e}")
            return None
        except requests.RequestException as e:
            self.problem(source, f"{label}: version lookup failed: {e}")
            return None

        if missing:
            self.problem(source, f"{label}: {missing}")
            return None

        click.secho(f"  ✓ {label}: {full_version}", fg="green")
        return full_version


def group_by_platform[T](items: list[T], platform_of: Callable[[T], str]) -> dict[str, list[T]]:
    """Groups `items` by platform name, keeping their order within each platform."""
    grouped: dict[str, list[T]] = {}
    for item in items:
        grouped.setdefault(platform_of(item), []).append(item)
    return grouped


def parse_platform_versions(value: str, check: SanityCheck) -> list[PlatformVersion]:
    """Parses the space-separated "<platform>=<version>" entries, recording every malformed one."""
    specs = value.split()
    if not specs:
        check.problem("PLATFORM_VERSIONS", "is empty, expected at least one <platform>=<version>")

    platform_versions = []
    for position, spec in enumerate(specs, 1):
        name, sep, version = spec.partition("=")
        if not sep:
            check.problem("PLATFORM_VERSIONS", f"entry #{position} '{spec}' is not <platform>=<version>")
        elif name not in TEST_SERVER_PLATFORMS:
            check.problem(
                "PLATFORM_VERSIONS",
                f"entry #{position} '{spec}' has an unknown platform '{name}', expected one of: "
                f"{', '.join(TEST_SERVER_PLATFORMS)}",
            )
        else:
            platform_versions.append(PlatformVersion(position, TEST_SERVER_PLATFORMS[name], version))

    return platform_versions


def load_topology_test_servers(topology_file: Path, check: SanityCheck) -> list[TopologyTestServer]:
    """Reads the topology's test servers, recording a missing or unreadable file and unknown platforms."""
    source = f"topology {topology_file.name}"
    if not topology_file.is_file():
        check.problem(source, f"{topology_file} does not exist")
        return []

    try:
        with open(topology_file) as fin:
            entries = json.load(fin).get("test_servers", [])
    except json.JSONDecodeError as e:
        check.problem(source, f"is not valid JSON: {e}")
        return []

    if not entries:
        check.problem(source, "has no test_servers")

    test_servers = [
        TopologyTestServer(index, str(entry.get("platform", "")), str(entry.get("location", "")))
        for index, entry in enumerate(entries)
    ]
    # Only a warning: a test server no entry asks for is not used, and a misspelled platform that an entry does ask
    # for shows up as too few test servers of it.
    for ts in test_servers:
        if ts.platform not in TEST_SERVER_PLATFORMS:
            click.secho(f"  ⚠ [{source}] {ts} has an unknown platform and will not be used", fg="yellow")

    return test_servers


def match_topology(
    platform_versions: list[PlatformVersion],
    test_servers: list[TopologyTestServer],
    topology_file: Path,
    check: SanityCheck,
) -> list[tuple[TopologyTestServer, PlatformVersion]]:
    """
    Gives each entry its own topology test server of the same platform: a platform's Nth entry goes to its Nth
    test server, in topology order. Test servers left over are not used. Once every platform is matched, records
    each platform the topology has too few test servers for. Returns the test servers used, in topology order,
    with their entries.
    """
    entries = group_by_platform(platform_versions, lambda pv: pv.platform.name)
    servers = group_by_platform(test_servers, lambda ts: ts.platform)

    matched: list[tuple[TopologyTestServer, PlatformVersion]] = []
    for name, platform_entries in entries.items():
        platform_servers = servers.get(name, [])
        if len(platform_entries) > len(platform_servers):
            check.problem(
                f"topology {topology_file.name}",
                f"{name}: PLATFORM_VERSIONS gives {len(platform_entries)} "
                f"({', '.join(map(str, platform_entries))}) but the topology has {len(platform_servers)}",
            )
        else:
            matched += zip(platform_servers, platform_entries, strict=False)

    return sorted(matched, key=lambda pair: pair[0].index)


def run_sanity_checks(
    platform_versions: str, sgw_version: str, topology_file: Path
) -> tuple[list[tuple[TopologyTestServer, str]], str]:
    """
    Checks the platform versions, the Sync Gateway version and the topology together, logging the outcome of each
    check and which version every test server gets. Exits with SANITY_CHECK_EXIT_CODE and every problem listed if
    any check fails. Returns the test servers to use, in topology order, with their full CBL versions, and the full
    Sync Gateway version.
    """
    check = SanityCheck()

    click.secho(f"🔎 Checking PLATFORM_VERSIONS against {topology_file.name}", fg="cyan", bold=True)
    entries = parse_platform_versions(platform_versions, check)
    for pv in entries:
        click.echo(f"  {pv}")

    test_servers = load_topology_test_servers(topology_file, check)
    # An unreadable topology is already recorded, and matching against it would only repeat that.
    assignment = match_topology(entries, test_servers, topology_file, check) if test_servers else []

    click.secho("🔎 Checking that every version exists", fg="cyan", bold=True)
    # Each distinct version is looked up once, however many entries share it.
    full_versions: dict[tuple[str, str], str | None] = {}
    for pv in entries:
        key = (pv.platform.name, pv.version)
        if key not in full_versions:
            product = pv.platform.proget_product
            full_versions[key] = check.existing_version("PLATFORM_VERSIONS", str(pv), product, product, pv.version)

    full_sgw_version = check.existing_version(
        "SGW_VERSION", f"Sync Gateway {sgw_version}", "sync-gateway", "sync_gateway", sgw_version
    )

    if check.problems:
        click.secho(f"\n💥 {len(check.problems)} problem(s) with the multiplatform input:", fg="red", bold=True)
        for problem in check.problems:
            click.secho(f"  {problem}", fg="red")
        sys.exit(SANITY_CHECK_EXIT_CODE)

    assert full_sgw_version is not None
    click.secho(
        f"\n✅ Test servers used from {topology_file.name}, with the entry and CBL version each gets:",
        fg="green",
        bold=True,
    )
    used: list[tuple[TopologyTestServer, str]] = []
    for ts, pv in assignment:
        version = full_versions[(pv.platform.name, pv.version)]
        assert version is not None
        click.echo(f"  {ts}  <-  {pv}  ->  CBL {version}")
        used.append((ts, version))
    click.echo(f"  Sync Gateway {full_sgw_version}")

    used_indexes = {ts.index for ts, _ in used}
    spare = [ts for ts in test_servers if ts.index not in used_indexes]
    if spare:
        click.secho(f"Not used ({len(spare)} spare test servers):", fg="yellow")
        for ts in spare:
            click.secho(f"  {ts}", fg="yellow")

    return used, full_sgw_version


def parse_platform_key(platform_key: str) -> tuple[str, str | None]:
    """
    Parse a platform key back into platform and target_os.

    Args:
        platform_key: Key like "dotnet_windows", "ios", "c_linux"

    Returns:
        Tuple of (platform, target_os) where target_os may be None
    """
    if "_" in platform_key:
        platform, target_os = platform_key.split("_", 1)
        return platform, target_os
    else:
        return platform_key, None


def run_platform_specific_setup(
    platform_key: str,
    full_version: str,
    sgw_version: str,
    target_os: str | None = None,
) -> None:
    """
    Run platform-specific setup scripts.

    Args:
        platform_key: Platform identifier (ios, android, dotnet, java, c)
        full_version: Full version string (version-build)
        sgw_version: Sync Gateway version
        target_os: Optional OS specification (windows, macos, linux, android, ios)
    """
    QE_dir = SCRIPT_DIR.parent

    # Find and run the main platform script
    if platform_key == "android":
        main_script = QE_dir / "android_tests.sh"
        if main_script.exists():
            # Android script expects: <cbl_version> <sg_version>
            # Android expects combined version (e.g., "3.2.3-6")
            cmd = ["bash", str(main_script), full_version, sgw_version]
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: android_tests.sh not found in {QE_dir}", fg="yellow")

    elif platform_key == "ios":
        main_script = QE_dir / "test.sh"
        if main_script.exists():
            # iOS test.sh expects: <edition> <version> <build_num> <sgw_version> [private_key]
            # iOS needs SEPARATE version and build number parameters
            if "-" in full_version:
                version, build_num = full_version.split("-", 1)
            else:
                raise click.BadParameter(
                    f"iOS platform requires explicit build number. Please specify as ios:{full_version}-<build>"
                )

            cmd = [
                "bash",
                str(main_script),
                "enterprise",
                version,
                build_num,
                sgw_version,
            ]
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: test.sh not found in {QE_dir}", fg="yellow")


@click.command()
@click.argument("platform_versions")
@click.argument("sgw_version")
@click.argument("topology_file", default="topology.json")
@click.option("--setup-only", is_flag=True, help="Only setup platforms, do not run tests")
def main(
    platform_versions: str,
    sgw_version: str,
    topology_file: str,
    setup_only: bool = False,
) -> None:
    """
    Setup multiplatform CBL testing environment.

    PLATFORM_VERSIONS: Space-separated "<platform>=<version>" list, one entry per test server to use, e.g.
    "swift_ios=4.1.0 swift_ios=4.2.0 dotnet_macos=4.1.0-18"
    SGW_VERSION: Sync Gateway version to use
    Optional:
    topology_file: Topology file in this directory to use (default: topology.json)
    """
    topology_path = SCRIPT_DIR / topology_file
    used, full_sgw_version = run_sanity_checks(platform_versions, sgw_version, topology_path)

    # setup_test() gives versions to every test server of the topology it reads, so it reads a copy holding only
    # the ones used.
    with open(topology_path) as fin:
        topology = json.load(fin)
    topology["test_servers"] = [topology["test_servers"][ts.index] for ts, _ in used]
    with tempfile.TemporaryDirectory() as tmp_dir:
        used_topology_path = Path(tmp_dir) / topology_path.name
        with open(used_topology_path, "w") as fout:
            json.dump(topology, fout, indent=4)

        setup_test(
            [version for _, version in used],
            [full_sgw_version],
            used_topology_path,
            SCRIPT_DIR / "config_multiplatform.json",
            "multiplatform",
            setup_dir="multiplatform",
        )
    click.secho("🎉 Multiplatform setup completed successfully!", fg="green", bold=True)


if __name__ == "__main__":
    main()
