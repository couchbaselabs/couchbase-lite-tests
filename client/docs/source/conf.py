# Configuration file for the Sphinx documentation builder.

# -- Project information

project = 'Couchbase Lite Python Test Client'
copyright = '2023, Couchbase'
author = 'Couchbase'

release = '0.1.5'
version = '0.1'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'autoapi.extension'
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

autoapi_dirs = ['../../src/cbltest']
autoapi_add_toctree_entry = True
html_theme = 'sphinx_rtd_theme'

def skip_private(app, what, name, obj, skip, options):
    return name.split('.')[-1].startswith("_")

def setup(sphinx):
    sphinx.connect("autoapi-skip-member", skip_private)