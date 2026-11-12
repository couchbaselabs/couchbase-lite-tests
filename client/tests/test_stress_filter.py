import pytest
from conftest import NestedPytest

pytest_plugins = ["pytester"]


@pytest.fixture
def suite(nested_pytest: NestedPytest) -> NestedPytest:
    """A suite with one regular test and one stress test."""
    nested_pytest.pytester.makepyfile(test_regular="def test_regular(): pass")
    stress = nested_pytest.pytester.mkdir("stress")
    (stress / "test_long.py").write_text("def test_long(): pass")
    return nested_pytest


def test_stress_tests_skipped_by_default(suite: NestedPytest) -> None:
    result = suite.pytester.runpytest_subprocess(*suite.args, "-v")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*test_regular.py::test_regular PASSED*"])


def test_stress_option_runs_only_stress_tests(suite: NestedPytest) -> None:
    result = suite.pytester.runpytest_subprocess(*suite.args, "-v", "--stress")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*stress/test_long.py::test_long PASSED*"])
