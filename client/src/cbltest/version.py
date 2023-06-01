from typing import Final

# For hatchling to easily detect the version
__version__ = "0.1.0"

# Typed version for outside use
VERSION: Final[str] = __version__

def available_api_version(version: int) -> int:
    """
    Checks that the passed API version exists
    
    :param version: The version to check
    """
    if version < 2:
        return version
    
    raise NotImplementedError(f"API version {version} does not exist!")