class CBLPyTestGlobal:
    running_test_name: str = "no-test"
    """Gets or sets the running test name so that the entire framework is aware of it"""

    auto_start_tdk_page: bool = True
    """Gets or sets whether or not to automatically launch the TDK browser page"""

    cbcollect_needed: bool = False
    """Set by CouchbaseCluster.create_database when a call to Sync Gateway times out with a
    real Couchbase Server present (the CBG-5733 signature of a CBS indexer race that leaves
    Sync Gateway retrying forever).  Read once, at session end, by the cbcollect_session
    fixture -- the same set-once-read-elsewhere pattern auto_start_tdk_page uses, needed here
    because create_database has no access to pytest.Config or the session-scoped fixtures
    that sgcollect/es_collect check testsfailed through."""
