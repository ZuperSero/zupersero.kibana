# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
---
module: kibana_request
short_description: Send an arbitrary Kibana API request
description:
  - Provides an escape hatch for non-resource Kibana API actions.
  - Read methods report no change; action methods explicitly report a change.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  path:
    description:
      - Kibana API path.
      - Must be relative; absolute and cross-origin URLs are rejected.
    type: str
    required: true
  method:
    description: HTTP method.
    type: str
    choices: [GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE]
    default: GET
  body:
    description: JSON request body.
    type: raw
  query:
    description: Query parameters encoded in deterministic key order.
    type: dict
  success_codes:
    description: Accepted HTTP response status codes.
    type: list
    elements: int
    default: [200, 201, 202, 204]
  response_path:
    description: Dot-separated path extracted from the response.
    type: str
  sensitive_fields:
    description: Dot-separated response fields redacted from output and failures.
    type: list
    elements: str
    default: []
notes:
  - In check mode, C(GET), C(HEAD), and C(OPTIONS) are performed normally.
  - In check mode, action methods are not sent and return I(changed=true).
"""

EXAMPLES = r"""
- name: Read Kibana status
  zupersero.kibana.kibana_request:
    path: /api/status
  register: status

- name: Run a non-idempotent action
  zupersero.kibana.kibana_request:
    path: /api/fleet/agents/some-agent/unenroll
    method: POST
    body:
      revoke: true
"""

RETURN = r"""
response:
  description: API response, optionally extracted with I(response_path).
  returned: when the request is performed
  type: raw
status:
  description: HTTP response status.
  returned: when the request is performed
  type: int
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


def run_module(
    module: AnsibleModule, client: kibana.KibanaClient | None = None
) -> None:
    """Execute an arbitrary Kibana request."""
    method = module.params["method"]
    changed = method not in ("GET", "HEAD", "OPTIONS")
    if module.check_mode and changed:
        module.exit_json(changed=True, response=None, status=None)

    client = client or kibana.KibanaClient(module)
    path = client.space_path(module.params["path"])
    status, response = client.request(
        method,
        path,
        data=module.params.get("body"),
        query=module.params.get("query"),
        sensitive_fields=module.params["sensitive_fields"],
    )
    if status not in module.params["success_codes"]:
        module.fail_json(
            msg=f"Kibana request {method} {path} failed with HTTP {status}",
            status=status,
            response=kibana.sanitize(
                response, module.params["sensitive_fields"]
            ),
        )
    extracted = kibana.extract_value(response, module.params.get("response_path"))
    module.exit_json(
        changed=changed,
        response=kibana.sanitize(
            extracted, module.params["sensitive_fields"]
        ),
        status=status,
    )


def main() -> None:
    argument_spec = kibana.kibana_argument_spec(include_state=False)
    argument_spec.update(
        path=dict(type="str", required=True),
        method=dict(
            type="str",
            choices=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
            default="GET",
        ),
        body=dict(type="raw"),
        query=dict(type="dict"),
        success_codes=dict(
            type="list", elements="int", default=[200, 201, 202, 204]
        ),
        response_path=dict(type="str"),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
