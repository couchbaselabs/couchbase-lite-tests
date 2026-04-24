"""Unit tests for CouchbaseVersion parsing (SyncGatewayVersion / EdgeServerVersion)
and GreenboardUploader version handling."""

from cbltest.api.edgeserver import EdgeServerVersion
from cbltest.api.syncgateway import SyncGatewayVersion


class TestSyncGatewayVersionParse:
    """Tests for SyncGatewayVersion.parse()"""

    def test_standard_3x_format(self):
        v = SyncGatewayVersion("3.3.3(271;abc123)")
        assert v.version == "3.3.3"
        assert v.build_number == 271

    def test_standard_4x_format(self):
        v = SyncGatewayVersion("4.0.0(350;def456)")
        assert v.version == "4.0.0"
        assert v.build_number == 350

    def test_missing_parentheses(self):
        v = SyncGatewayVersion("4.0.0")
        assert v.version == "unknown"
        assert v.build_number == 0

    def test_missing_semicolon(self):
        v = SyncGatewayVersion("4.0.0(271)")
        assert v.version == "unknown"
        assert v.build_number == 0

    def test_empty_version_before_lparen(self):
        """Previously returned ("", 271) — now returns ("unknown", 271)."""
        v = SyncGatewayVersion("(271;abc)")
        assert v.version == "unknown"
        assert v.build_number == 271

    def test_non_numeric_build(self):
        """Non-numeric build between ( and ; should not crash."""
        v = SyncGatewayVersion("4.0.0(abc;def)")
        assert v.version == "4.0.0"
        assert v.build_number == 0

    def test_version_with_spaces(self):
        v = SyncGatewayVersion("4.0.0 (271;commit)")
        assert v.version == "4.0.0"
        assert v.build_number == 271

    def test_empty_input(self):
        v = SyncGatewayVersion("")
        assert v.version == "unknown"
        assert v.build_number == 0

    def test_raw_preserved(self):
        v = SyncGatewayVersion("3.3.3(271;abc)")
        assert v.raw == "3.3.3(271;abc)"

    def test_enterprise_edition_suffix(self):
        """Handle version strings like '4.0.0(271;commit) EE'."""
        v = SyncGatewayVersion("4.0.0(271;commit) EE")
        assert v.version == "4.0.0"
        assert v.build_number == 271


class TestEdgeServerVersionParse:
    """Tests for EdgeServerVersion.parse() — same logic as SyncGatewayVersion."""

    def test_standard_format(self):
        v = EdgeServerVersion("1.2.0(100;abc)")
        assert v.version == "1.2.0"
        assert v.build_number == 100

    def test_empty_version_before_lparen(self):
        v = EdgeServerVersion("(100;abc)")
        assert v.version == "unknown"
        assert v.build_number == 100

    def test_non_numeric_build(self):
        v = EdgeServerVersion("1.0.0(xyz;abc)")
        assert v.version == "1.0.0"
        assert v.build_number == 0

    def test_no_parentheses(self):
        v = EdgeServerVersion("1.0.0")
        assert v.version == "unknown"
        assert v.build_number == 0
