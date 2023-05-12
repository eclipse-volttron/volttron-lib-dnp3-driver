# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2022 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

import os
import subprocess
import yaml

# Configuration file for the Sphinx documentation builder.

# -- Project information

project = 'VOLTTRON DNP3 Driver'
copyright = '2022, Pacific Northwest National Lab'
author = 'Pacific Northwest National Lab'

release = '0.1'
version = '0.1.0'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'

# -- Options for EPUB output
# epub_show_urls = 'footnote'

# Custom event handlers for Volttron #
def setup(app):
    """
    Registers callback method on sphinx events. callback method used to
    dynamically generate api-docs rst files which are then converted to html
    by readthedocs
    :param app:
    """
    # app.connect('builder-inited', generate_apidoc)
    app.connect('builder-inited', generate_agent_docs)

    # app.connect('build-finished', clean_api_rst)
    app.connect('build-finished', clean_agent_docs_rst)

script_dir = os.path.dirname(os.path.realpath(__file__))
agent_docs_root = os.path.join(script_dir, "agent-docs")

def _read_config(filename):
    data = {}
    try:
        with open(filename, 'r') as yaml_file:
            data = yaml.safe_load(yaml_file)
    except IOError as exc:
        print("Error reading from file: {}".format(filename))
        raise exc
    except yaml.YAMLError as exc:
        print("Yaml Error: {}".format(filename))
        raise exc
    return data


def generate_agent_docs(app):
    os.makedirs(agent_docs_root)
    agents_data = _read_config(filename=os.path.join(script_dir, "agent_versions.yml"))
    repo_prefix = "https://github.com/eclipse-volttron/"
    for agent_name in agents_data:
        agent_repo = agents_data[agent_name].get("repo")
        if not agent_repo:
            agent_repo = repo_prefix + agent_name
        subprocess.check_call(["git", "clone", "--no-checkout", agent_repo], cwd=agent_docs_root)
        # for 1st version not doing api-docs. If doing api-docs do full checkout, install requirements, run api-docs
        agent_clone_dir = os.path.join(agent_docs_root, agent_name)
        agent_version = agents_data[agent_name]["version"]
        subprocess.check_call(["git", "checkout", agent_version], cwd=agent_clone_dir)
        docs_source_dir = agents_data[agent_name].get("docs_dir", "docs/source")
        subprocess.check_call(["git", "sparse-checkout", "set", docs_source_dir], cwd=agent_clone_dir)


def clean_agent_docs_rst(app, exception):
    """
    Deletes folder containing all auto generated .rst files at the end of
    sphinx build immaterial of the exit state of sphinx build.
    :param app:
    :param exception:
    """
    global agent_docs_root
    import shutil
    if os.path.exists(agent_docs_root):
        print("Cleanup: Removing agent docs clone directory {}".format(agent_docs_root))
        shutil.rmtree(agent_docs_root)
