from pathlib import Path
from typing import Final

SCRIPT_DIR = Path(__file__).parent

STACK_NAME: Final[str] = "backend"
AWS_TAG_NAME: Final[str] = "mobile-e2e"
AMAZON_LINUX_2023: Final[str] = "ami-05576a079321f21f8"
WORK_DIR: Final[Path] = SCRIPT_DIR
