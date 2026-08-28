# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage an Elastic Agent binary download source."""

DOCUMENTATION = r"""
---
module: agent_download_source
short_description: Manage an Elastic Agent download source
description: Create, update, and remove a Fleet Agent binary download source.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id: {description: Server-generated download-source identifier., type: str}
  name: {description: Download source name., type: str}
  host: {description: Agent binary repository URL., type: str}
  proxy_id: {description: Fleet proxy identifier., type: str}
  is_default: {description: Make this the default download source., type: bool, default: false}
  ssl: {description: Download-source TLS settings., type: dict}
  secrets: {description: Download-source secret references or values., type: dict}
  sensitive_fields: {description: Response paths to redact., type: list, elements: str, default: []}
  replace: {description: Reserved for future authoritative replacement support., type: bool, default: false}
  state: {description: Desired source state., type: str, choices: [present, absent], default: present}
"""
EXAMPLES = r"""
- name: Configure Agent downloads
  zupersero.kibana.agent_download_source:
    name: Internal artifacts
    host: https://artifacts.example.test/elastic-agent
    is_default: true
"""
RETURN = r"""
agent_download_source:
  description: Current or resulting source with sensitive values redacted.
  returned: always
  type: dict
status: {description: HTTP status of the last operation., returned: always, type: int}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource  # noqa: E402


CONFIG = {
    "service": "agent_download_sources", "resource": "download source", "result": "agent_download_source", "required": ("name", "host"),
    "fields": ("name", "host", "proxy_id", "is_default", "ssl", "secrets"),
    "spec": {
        "host": dict(type="str"), "proxy_id": dict(type="str"), "is_default": dict(type="bool", default=False),
        "ssl": dict(type="dict", no_log=True), "secrets": dict(type="dict", no_log=True),
    },
}


def agent_download_source_argument_spec():
    return fleet_resource.argument_spec(CONFIG)


def main():
    module = AnsibleModule(
        argument_spec=agent_download_source_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    fleet_resource.run_module(module, kibana.KibanaClient(module), CONFIG)


if __name__ == "__main__":
    main()
