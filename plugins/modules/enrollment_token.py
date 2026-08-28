# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage a Kibana Fleet enrollment token."""

DOCUMENTATION = r"""
---
module: enrollment_token
short_description: Manage a Kibana Fleet enrollment token
description: Create and revoke Fleet enrollment API keys for an agent policy.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id: {description: Enrollment API-key identifier., type: str}
  name: {description: Token name used for exact lookup., type: str}
  policy_id: {description: Agent policy identifier., type: str}
  expiration: {description: Optional token expiration duration., type: str}
  sensitive_fields: {description: Response paths to redact., type: list, elements: str, default: []}
  replace: {description: Reserved for future authoritative replacement support., type: bool, default: false}
  state: {description: Desired token state; absent revokes the token., type: str, choices: [present, absent], default: present}
notes:
  - The generated api_key is returned only in redacted form by this module.
  - Enrollment token creation is idempotent by exact name and policy_id.
"""
EXAMPLES = r"""
- name: Create an enrollment token
  zupersero.kibana.enrollment_token:
    name: Application agents
    policy_id: application-policy
    expiration: 30d
"""
RETURN = r"""
enrollment_token:
  description: Current or resulting enrollment token with api_key redacted.
  returned: always
  type: dict
status: {description: HTTP status of the last operation., returned: always, type: int}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource  # noqa: E402


CONFIG = {
    "service": "enrollment_tokens", "resource": "enrollment token", "result": "enrollment_token", "required": ("policy_id",),
    "fields": ("name", "policy_id", "expiration"),
    "spec": {"policy_id": dict(type="str"), "expiration": dict(type="str")},
}


def enrollment_token_argument_spec():
    return fleet_resource.argument_spec(CONFIG)


def main():
    module = AnsibleModule(
        argument_spec=enrollment_token_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    fleet_resource.run_module(module, kibana.KibanaClient(module), CONFIG)


if __name__ == "__main__":
    main()
