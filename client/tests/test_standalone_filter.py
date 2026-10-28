from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_ARGS = ("--config", str(Path(__file__).parent / "empty_config.json"), "-p", "no:randomly", "-rs")

_TEST_FILE = """
import pytest


@pytest.mark.standalone
def test_standalone():
    pass


@pytest.mark.standalone
class TestStandalone:
    @pytest.mark.parametrize("n", [1, 2])
    def test_param(self, n):
        pass


def test_regular():
    pass
"""


@pytest.fixture
def suite(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makepyfile(test_suite=_TEST_FILE)
    return pytester


def test_skipped_by_default(suite: pytest.Pytester) -> None:
    result = suite.runpytest(*_ARGS)
    result.assert_outcomes(passed=1, skipped=3)
    result.stdout.fnmatch_lines(["*Standalone test: run it by naming it on the command line*"])


def test_skipped_when_directory_named(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, ".").assert_outcomes(passed=1, skipped=3)


def test_skipped_before_fixtures(suite: pytest.Pytester) -> None:
    suite.makeconftest(
        """
import pytest


@pytest.fixture(autouse=True)
def reset_backend():
    raise AssertionError("fixture ran for a skipped test")
"""
    )
    # Only test_regular sets up the fixture
    suite.runpytest(*_ARGS).assert_outcomes(errors=1, skipped=3)


def test_runs_when_named_by_node_id(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "test_suite.py::test_standalone").assert_outcomes(passed=1)


def test_runs_every_parametrization_when_named_without_parameters(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "test_suite.py::TestStandalone::test_param").assert_outcomes(passed=2)


def test_runs_one_parametrization_when_named_with_parameters(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "test_suite.py::TestStandalone::test_param[1]").assert_outcomes(passed=1)


def test_runs_when_file_named(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "test_suite.py").assert_outcomes(passed=4)


def test_only_named_test_runs_when_directory_also_named(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "test_suite.py::test_standalone", ".").assert_outcomes(passed=2, skipped=2)


def test_all_run_when_selected_by_marker(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "-m", "standalone").assert_outcomes(passed=3, deselected=1)


def test_deselected_by_marker_expression(suite: pytest.Pytester) -> None:
    suite.runpytest(*_ARGS, "-m", "not standalone").assert_outcomes(passed=1, deselected=3)
