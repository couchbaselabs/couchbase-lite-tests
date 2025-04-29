"""
This module provides utility functions for console output operations

Functions:
    header(text: str) -> None:
        Print a green text header that makes the message very obvious
"""

from termcolor import colored


def header(text: str) -> None:
    """
    Print a green text header that makes the message very obvious

    === It looks like this ==

    Args:
        text (str): The text to print
    """
    print()
    print(colored(f"=== {text} ===", "green"))
    print()
