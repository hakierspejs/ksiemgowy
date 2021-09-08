import sys

sys.path.append("../..")
project = "ksiemgowy"
copyright = "2021, Hakierspejs"
author = "Hakierspejs"
extensions = ["sphinx.ext.autodoc"]
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "alabaster"
html_static_path = ["_static"]
