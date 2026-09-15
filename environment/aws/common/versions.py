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
