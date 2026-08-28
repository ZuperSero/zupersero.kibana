# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage a Kibana Fleet Server host."""

DOCUMENTATION = r"""
---
module: fleet_server_host
short_description: Manage a Kibana Fleet Server host
description: Create, update, and remove a Fleet Server host configuration.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id: {description: Server-generated host identifier., type: str}
  name: {description: Fleet Server host name., type: str}
  host_urls: {description: Fleet Server URLs., type: list, elements: str}
  proxy_id: {description: Fleet proxy identifier., type: str}
  ssl: {description: Fleet Server TLS settings., type: dict}
  secrets: {description: Fleet Server secret references or values., type: dict}
  sensitive_fields: {description: Response paths to redact., type: list, elements: str, default: []}
  replace: {description: Reserved for future authoritative replacement support., type: bool, default: false}
  state: {description: Desired host state., type: str, choices: [present, absent], default: present}
"""
EXAMPLES = r"""
- name: Configure Fleet Server
  zupersero.kibana.fleet_server_host:
    name: Primary Fleet Server
    host_urls: [https://fleet.example.test:8220]
"""
RETURN = r"""
fleet_server_host:
  description: Current or resulting Fleet Server host with sensitive values redacted.
  returned: always
  type: dict
status: {description: HTTP status of the last operation., returned: always, type: int}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource  # noqa: E402


CONFIG = {
    "service": "fleet_server_hosts", "resource": "server host", "result": "fleet_server_host", "required": ("name", "host_urls"),
    "fields": ("name", "host_urls", "proxy_id", "ssl", "secrets"),
    "spec": {
        "host_urls": dict(type="list", elements="str"), "proxy_id": dict(type="str"),
        "ssl": dict(type="dict", no_log=True), "secrets": dict(type="dict", no_log=True),
    },
}


def fleet_server_host_argument_spec():
    return fleet_resource.argument_spec(CONFIG)


def main():
    module = AnsibleModule(
        argument_spec=fleet_server_host_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    fleet_resource.run_module(module, kibana.KibanaClient(module), CONFIG)


if __name__ == "__main__":
    main()
