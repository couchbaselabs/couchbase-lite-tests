import json
import subprocess
from enum import Enum
from typing import Any


class OutputType(Enum):
    RAW = "raw"
    JSON = "json"


def get_terraform_output(
    directory: str, *, name: str | None = None, type: OutputType | None = None
) -> str:
    """
    Get the output value from Terraform state.

    Args:
        directory (str): The directory where the Terraform configuration is located.
        name (str): The name of the output variable.
        type (OutputType | None): The type of output to retrieve (raw or json).
    """
    command = [
        "terraform",
        "output",
    ]

    if type == OutputType.JSON:
        command.append("-json")
    elif type == OutputType.RAW:
        command.append("-raw")

    if name:
        command.append(name)

    result = subprocess.run(
        command,
        cwd=directory,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command '{' '.join(command)}' failed with exit status {result.returncode}: {result.stderr}"
        )

    return result.stdout.strip()


def get_terraform_json(directory: str, *, name: str | None = None) -> Any:
    """
    Get all Terraform outputs in JSON format.

    Args:
        directory (str): The directory where the Terraform configuration is located.
        name (str): The name of the output variable.
    """
    output_str = get_terraform_output(directory, name=name, type=OutputType.JSON)
    return json.loads(output_str)
