"""Unit tests for CouchbaseVersion parsing (SyncGatewayVersion / EdgeServerVersion)
and GreenboardUploader version handling."""

import packaging.version
import pytest
from cbltest.api.edgeserver import EdgeServerVersion
from cbltest.api.syncgateway import SyncGatewayVersion


class TestSyncGatewayVersionParse:
    """Tests for SyncGatewayVersion.parse()"""

    @pytest.mark.parametrize(
        "version_string, expected_version, expected_build",
        [
            ("3.3.3(271;abc123)", "3.3.3", 271),
            ("3.3.3 (271;abc123)", "3.3.3", 271),
            ("4.0.0(350;def456)", "4.0.0", 350),
            ("4.0.0 (350;def456)", "4.0.0", 350),
            ("4.0.0", "4.0.0", 0),
            ("4.0.0(271)", "4.0.0", 271),
            ("4.0.0 (271)", "4.0.0", 271),
            ("(271;abc)", "unknown", 271),
            ("4.0.0(abc;def)", "4.0.0", 0),
            ("4.0.0 (abc;def)", "4.0.0", 0),
            ("4.0.0(271;commit)", "4.0.0", 271),
            ("4.0.0 (271;commit)", "4.0.0", 271),
            ("", "unknown", 0),
            ("4.0.0(271;commit) EE", "4.0.0", 271),
            ("Couchbase Sync Gateway/3.3.3(271;abc123)", "3.3.3", 271),
            ("Couchbase Sync Gateway/3.3.3 (271;abc123)", "3.3.3", 271),
            ("Couchbase Sync Gateway/4.0.0(350;def456)", "4.0.0", 350),
            ("Couchbase Sync Gateway/4.0.0 (350;def456)", "4.0.0", 350),
            ("Couchbase Sync Gateway/4.0.0", "4.0.0", 0),
            ("Couchbase Sync Gateway/4.0.0(271)", "4.0.0", 271),
            ("Couchbase Sync Gateway/4.0.0 (271)", "4.0.0", 271),
            ("Couchbase Sync Gateway/(271;abc)", "unknown", 271),
            ("Couchbase Sync Gateway/ (271;abc)", "unknown", 271),
            ("Couchbase Sync Gateway/4.0.0(abc;def)", "4.0.0", 0),
            ("Couchbase Sync Gateway/4.0.0 (abc;def)", "4.0.0", 0),
            ("Couchbase Sync Gateway/4.0.0 (271;commit)", "4.0.0", 271),
            ("Couchbase Sync Gateway/4.0.0(271;commit) EE", "4.0.0", 271),
        ],
    )
    def test_parse(self, version_string, expected_version, expected_build):
        v = SyncGatewayVersion(version_string)
        assert v.version == expected_version
        assert v.build_number == expected_build
        assert v.raw == version_string
        if v.version != "unknown":
            packaging.version.parse(v.version)


class TestEdgeServerVersionParse:
    """Tests for EdgeServerVersion.parse() — same logic as SyncGatewayVersion."""

    @pytest.mark.parametrize(
        "version_string, expected_version, expected_build",
        [
            ("1.2.0(100;abc)", "1.2.0", 100),
            ("(100;abc)", "unknown", 100),
            ("1.0.0(xyz;abc)", "1.0.0", 0),
            ("1.0.0", "unknown", 0),
        ],
    )
    def test_parse(self, version_string, expected_version, expected_build):
        v = EdgeServerVersion(version_string)
        assert v.version == expected_version
        assert v.build_number == expected_build
