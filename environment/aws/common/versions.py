import requests

_PROGET_BASE = "http://proget.build.couchbase.com:8080/api"


def resolve_latest_version(product: str, version_prefix: str | None = None) -> str:
    """
    Resolve the latest released version of `product` via the internal proget API.

    If `version_prefix` is given, resolves the latest release matching that
    major[.minor] prefix; otherwise resolves the true latest release.
    """
    url = f"{_PROGET_BASE}/latest_release?product={product}"
    if version_prefix:
        url += f"&version={version_prefix}"

    r = requests.get(url)
    r.raise_for_status()
    return str(r.json()["version"])


_LATESTBUILDS_BASE = "https://latestbuilds.service.couchbase.com/builds/latestbuilds"


def find_missing_version(product: str, version: str) -> str | None:
    """
    Checks that `version` ("x.y.z" or "x.y.z-<build>") of `product` exists, returning why it doesn't, or None when
    it does. The version must be known to proget, and a pinned build must also be on latestbuilds.
    """
    base_version, _, build = version.partition("-")
    r = requests.get(f"{_PROGET_BASE}/get_version", params={"product": product, "version": base_version}, timeout=30)
    if r.status_code == 404:
        return f"{product} {base_version} does not exist on proget"
    r.raise_for_status()

    # Build 0 denotes the release itself, which must already have been released.
    if build == "0" and not r.json().get("IsRelease", False):
        return f"{product} {base_version} has no release to use for build 0"
    if build and build != "0":
        r = requests.head(f"{_LATESTBUILDS_BASE}/{product}/{base_version}/{build}/", timeout=30)
        if r.status_code == 404:
            return f"{product} {base_version} has no build {build} on latestbuilds"
        r.raise_for_status()

    return None
