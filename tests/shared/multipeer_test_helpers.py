from cbltest.api.multipeer_replicator_types import MultipeerTransportType


def build_group_transports(
    size: int,
    transport: str,
) -> list[MultipeerTransportType]:
    """
    Builds a list of transports for a group of given size.

    If transport != "MIXED_MODE", returns a uniform list.
    If MIXED_MODE, distributes WIFI, BLUETOOTH, and ALL.
    """

    if transport != "MIXED_MODE":
        return [MultipeerTransportType.from_string(transport)] * size

    if size == 1:
        return [MultipeerTransportType.ALL]

    if size == 2:
        return [MultipeerTransportType.BLUETOOTH, MultipeerTransportType.ALL]

    # General distribution
    num_wifi = size // 3
    num_bt = size // 3
    num_dual = size - num_wifi - num_bt

    transports_array = (
        [MultipeerTransportType.WIFI] * num_wifi
        + [MultipeerTransportType.BLUETOOTH] * num_bt
        + [MultipeerTransportType.ALL] * num_dual
    )

    return transports_array
