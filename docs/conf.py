# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'World Historical Gazetteer'
copyright = '2024, World Historical Gazetteer'
author = 'Stephen Gadd'
release = '0.0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
import os
import sys
sys.path.insert(0, os.path.abspath('..'))  # Add the project root to the path (for access to README.md, etc.)

extensions = ['myst_parser']

myst_enable_extensions = [
    "amsmath",         # for math support
    "colon_fence",     # for colon-fenced code blocks
    "deflist",         # for definition lists
    "html_admonition", # for HTML-style admonitions
    "html_image",      # for <img> tags
    "replacements",    # for simple text replacements
    "smartquotes",     # for smart quotes
    "substitution",    # for substitution definitions
    "tasklist",        # for GitHub-style task lists
]

# Allow parsing of standard Markdown headers (#, ##, etc.)
myst_heading_anchors = 5

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
