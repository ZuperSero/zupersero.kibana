# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
---
module: kibana_info
short_description: Read or list arbitrary Kibana API objects
description:
  - Performs a read-only Kibana API request.
  - Can collect conventional page/per_page API responses.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  path:
    description:
      - Kibana API path to read.
      - Must be relative; absolute and cross-origin URLs are rejected.
    type: str
    required: true
  query:
    description: Query parameters encoded in deterministic key order.
    type: dict
  response_path:
    description: Dot-separated path containing the object or object list.
    type: str
  paginate:
    description: Collect a conventional page/per_page response.
    type: bool
    default: false
  page_parameter:
    description: Query parameter containing the page number.
    type: str
    default: page
  per_page_parameter:
    description: Query parameter containing the page size.
    type: str
    default: per_page
  page_size:
    description: Number of objects requested per page.
    type: int
    default: 100
  max_pages:
    description: Safety limit for pagination.
    type: int
    default: 100
  success_codes:
    description: Accepted HTTP response status codes.
    type: list
    elements: int
    default: [200]
  sensitive_fields:
    description: Dot-separated response fields redacted from output and failures.
    type: list
    elements: str
    default: []
"""

EXAMPLES = r"""
- name: Read Kibana status
  zupersero.kibana.kibana_info:
    path: /api/status

- name: List all connectors
  zupersero.kibana.kibana_info:
    path: /api/actions/connectors
    response_path: connectors
"""

RETURN = r"""
objects:
  description: Extracted objects, always represented as a list.
  returned: always
  type: list
  elements: raw
response:
  description: Last raw API response.
  returned: always
  type: raw
status:
  description: HTTP response status.
  returned: always
  type: int
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


def run_module(
    module: AnsibleModule, client: kibana.KibanaClient | None = None
) -> None:
    """Read arbitrary Kibana information."""
    client = client or kibana.KibanaClient(module)
    if module.params["page_size"] < 1:
        module.fail_json(msg="`page_size` must be greater than zero")
    if module.params["max_pages"] < 1:
        module.fail_json(msg="`max_pages` must be greater than zero")
    path = client.space_path(module.params["path"])
    if module.params["paginate"]:
        if not module.params.get("response_path"):
            module.fail_json(msg="`response_path` is required when `paginate=true`")
        status, objects, response = client.paginate(
            path,
            module.params["response_path"],
            query=module.params.get("query"),
            page_parameter=module.params["page_parameter"],
            per_page_parameter=module.params["per_page_parameter"],
            page_size=module.params["page_size"],
            max_pages=module.params["max_pages"],
            sensitive_fields=module.params["sensitive_fields"],
        )
    else:
        status, response = client.request(
            "GET",
            path,
            query=module.params.get("query"),
            sensitive_fields=module.params["sensitive_fields"],
        )
        extracted = kibana.extract_value(
            response, module.params.get("response_path")
        )
        if extracted is None:
            objects = []
        elif isinstance(extracted, list):
            objects = extracted
        else:
            objects = [extracted]
    if status not in module.params["success_codes"]:
        module.fail_json(
            msg=f"Kibana info read {path} failed with HTTP {status}",
            status=status,
            response=kibana.sanitize(
                response, module.params["sensitive_fields"]
            ),
        )
    module.exit_json(
        changed=False,
        objects=kibana.sanitize(
            objects, module.params["sensitive_fields"]
        ),
        response=kibana.sanitize(
            response, module.params["sensitive_fields"]
        ),
        status=status,
    )


def main() -> None:
    argument_spec = kibana.kibana_argument_spec(include_state=False)
    argument_spec.update(
        path=dict(type="str", required=True),
        query=dict(type="dict"),
        response_path=dict(type="str"),
        paginate=dict(type="bool", default=False),
        page_parameter=dict(type="str", default="page"),
        per_page_parameter=dict(type="str", default="per_page"),
        page_size=dict(type="int", default=100),
        max_pages=dict(type="int", default=100),
        success_codes=dict(type="list", elements="int", default=[200]),
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
