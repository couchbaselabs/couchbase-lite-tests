from typing import Any

# Configuration file for the Sphinx documentation builder.

# -- Project information

project = "Couchbase Lite Python Test Client"
copyright = "2023, Couchbase"
author = "Couchbase"

release = "1.2.0"
version = "1.2"

# -- General configuration

extensions = [
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "autoapi.extension",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}
intersphinx_disabled_domains = ["std"]

templates_path = ["_templates"]

autoapi_dirs = ["../../src/cbltest"]
autoapi_ignore = ["*/plugins/*"]
autodoc_inherit_docstrings = True
html_theme = "sphinx_rtd_theme"


def skip_private(app: Any, what: str, name: str, obj: Any, skip: bool, options: Any) -> bool:
    return skip or name.split(".")[-1].startswith("_")


def setup(sphinx: Any) -> None:
    sphinx.connect("autoapi-skip-member", skip_private)
