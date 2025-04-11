"""
This module provides utility functions for console output operations

Functions:
    header(text: str) -> None:
        Print a green text header that makes the message very obvious
"""

import click


def header(text: str) -> None:
    """
    Print a green text header that makes the message very obvious

    === It looks like this ==

    Args:
        text (str): The text to print
    """

    click.echo()
    click.secho(f"=== {text} ===", fg="green")
    click.echo()
