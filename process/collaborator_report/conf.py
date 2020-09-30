# Configuration file for the Sphinx documentation builder.
# -- Project information -----------------------------------------------------

project = 'Global Liveability Indicators, preliminary report: Maiduguri'
copyright = '2020, Global Healthy Liveable Cities Indicator Study Collaboration'
author = 'Global Healthy Liveable Cities Indicator Study Collaboration'

# The full version, including alpha/beta/rc tags
release = '1.1'
# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
# sys.path.append(os.path.abspath('../process'))
sys.path.insert(0, os.path.abspath('../process'))

# The master toctree document.
master_doc = 'index'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.coverage', 'sphinx.ext.napoleon','sphinx.ext.todo','sphinxcontrib.bibtex']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = "alabaster"
html_theme = "sphinx_rtd_theme"
pygments_style = 'sphinx'

html_theme_path = ["_themes", ]
# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# -- Custom changes --------------------------------------------------------

autodoc_mock_imports = ['_project_setup']

html_theme_options = {
    # 'canonical_url': '',
    # 'analytics_id': 'UA-XXXXXXX-1',  #  Provided by Google in your dashboard
    # 'logo_only': False,
    # 'display_version': True,
    # 'prev_next_buttons_location': 'bottom',
    # 'style_external_links': False,
    # 'vcs_pageview_mode': '',
    # 'style_nav_header_background': 'white',
    # # Toc options
    # 'collapse_navigation': True,
    # 'sticky_navigation': True,
    # 'navigation_depth': 4,
    # 'includehidden': True,
    # 'titles_only': False
    #'style_nav_header_background':'#2ca25f'
}

# Latex settings
latex_engine = 'xelatex'
latex_use_xindy = True
latex_elements = {
    'papersize': 'a4paper',
    'figure_align': 'H',
    'preamble':r'''
\usepackage{multirow,changepage,array,booktabs,caption,makecell}
''',
}

# Enable display of todo notes
todo_include_todos = True

