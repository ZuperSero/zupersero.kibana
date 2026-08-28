# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage a Kibana Fleet proxy."""

DOCUMENTATION = r"""
---
module: fleet_proxy
short_description: Manage a Kibana Fleet proxy
description: Create, update, and remove a Fleet HTTP proxy.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id: {description: Server-generated proxy identifier., type: str}
  name: {description: Proxy name., type: str}
  proxy_url: {description: Proxy URL., type: str}
  certificate: {description: Proxy client certificate., type: str}
  certificate_authorities: {description: Proxy CA certificate., type: str}
  certificate_key: {description: Proxy private key., type: str}
  proxy_headers: {description: Headers sent through the proxy., type: dict}
  sensitive_fields: {description: Response paths to redact., type: list, elements: str, default: []}
  replace: {description: Reserved for future authoritative replacement support., type: bool, default: false}
  state: {description: Desired proxy state., type: str, choices: [present, absent], default: present}
"""
EXAMPLES = r"""
- name: Configure Fleet proxy
  zupersero.kibana.fleet_proxy:
    name: Egress proxy
    proxy_url: http://proxy.example.test:8080
"""
RETURN = r"""
fleet_proxy:
  description: Current or resulting proxy with sensitive values redacted.
  returned: always
  type: dict
status: {description: HTTP status of the last operation., returned: always, type: int}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource  # noqa: E402


CONFIG = {
    "service": "fleet_proxies", "resource": "proxy", "result": "fleet_proxy", "required": ("name", "proxy_url"),
    "fields": ("name", "proxy_url", "certificate", "certificate_authorities", "certificate_key", "proxy_headers"),
    "field_map": {"proxy_url": "url"},
    "spec": {
        "proxy_url": dict(type="str"), "certificate": dict(type="str", no_log=True),
        "certificate_authorities": dict(type="str", no_log=True), "certificate_key": dict(type="str", no_log=True),
        "proxy_headers": dict(type="dict", no_log=True),
    },
}


def fleet_proxy_argument_spec():
    return fleet_resource.argument_spec(CONFIG)


def main():
    module = AnsibleModule(
        argument_spec=fleet_proxy_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    fleet_resource.run_module(module, kibana.KibanaClient(module), CONFIG)


if __name__ == "__main__":
    main()
