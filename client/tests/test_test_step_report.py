from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_ARGS = ("--config", str(Path(__file__).parent / "empty_config.json"), "-p", "no:randomly")

_TEST_FILE = """
from cbltest.api.cbltestclass import CBLTestClass


class TestSteps(CBLTestClass):
    def test_fails(self):
        self.mark_test_step("first step")
        self.mark_test_step('''
            second step
            with two lines
        ''')
        assert False

    def test_passes(self):
        self.mark_test_step("only step")
"""


def test_last_step_shown_on_failure(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_TEST_FILE)
    result = pytester.runpytest(*_ARGS)
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(
        ["*TestSteps.test_fails*", "Last test step (2):", "*second step", "*with two lines", "", "self = *"]
    )
    assert result.stdout.str().count("Last test step") == 1


_NESTED_TEST_FILE = """
from cbltest.api.cbltestclass import CBLTestClass


class TestSteps(CBLTestClass):
    def test_nested(self):
        self.mark_test_step("only step")
        try:
            raise KeyError("inner")
        except KeyError as e:
            raise RuntimeError("outer") from e
"""


def test_last_step_shown_once_for_nested_exceptions(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_NESTED_TEST_FILE)
    result = pytester.runpytest(*_ARGS)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*TestSteps.test_nested*",
            "Last test step (1): only step",
            "",
            "self = *",
            "*KeyError: 'inner'",
            "*direct cause of the following exception*",
            "self = *",
            "*RuntimeError: outer",
        ]
    )
    assert result.stdout.str().count("Last test step") == 1
