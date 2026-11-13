from pathlib import Path

import pytest

from environment.aws.topology_setup.setup_topology import TopologyConfig


@pytest.mark.parametrize("count", [0, 1, 3])
def test_count(count: int) -> None:
    assert TopologyConfig(config_input={"load_balancers": count}).total_lb_count == count


def test_old_list_gives_one_per_entry(capsys: pytest.CaptureFixture[str]) -> None:
    config = TopologyConfig(config_input={"load_balancers": [{"sync_gateways": [0, 1, 2]}, {"sync_gateways": [3, 4]}]})

    assert config.total_lb_count == 2
    assert "deprecated" in capsys.readouterr().out


def test_old_empty_list_gives_none(capsys: pytest.CaptureFixture[str]) -> None:
    assert TopologyConfig(config_input={"load_balancers": []}).total_lb_count == 0
    assert capsys.readouterr().out == ""


def test_old_list_counts_toward_include(tmp_path: Path) -> None:
    child = tmp_path / "child.json"
    child.write_text('{"load_balancers": [{"sync_gateways": [0]}]}')
    parent = tmp_path / "parent.json"
    parent.write_text('{"load_balancers": 1, "include": "child.json"}')

    assert TopologyConfig(parent).total_lb_count == 2


@pytest.mark.parametrize("value", [-1, True, "2", 1.5, [1], [{"sync_gateways": [0]}, 2]])
def test_invalid_raises(value: object) -> None:
    with pytest.raises(ValueError, match="load_balancers"):
        TopologyConfig(config_input={"load_balancers": value})
