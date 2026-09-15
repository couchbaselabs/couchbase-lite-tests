class CBLPyTestGlobal:
    running_test_name: str = "no-test"
    """Gets or sets the running test name so that the entire framework is aware of it"""

    auto_start_tdk_page: bool = True
    """Gets or sets whether or not to automatically launch the TDK browser page"""

    cbcollect_needed: bool = False
    """Set by SyncGatewayCluster.create_database when its PUT call times out with a real
    Couchbase Server present.  Read once, at session end, by the cbcollect_session fixture --
    the same set-once-read-elsewhere pattern auto_start_tdk_page uses."""
