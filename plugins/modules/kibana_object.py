# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DOCUMENTATION = r"""
---
module: kibana_object
short_description: Manage an arbitrary Kibana API object
description:
  - Manages an object exposed by a Kibana API when no typed module is available.
  - Reads current state before creating, updating, or deleting the object.
  - The item path can contain C({id}); I(id) is URL-quoted before substitution.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  path:
    description:
      - API path used to read, update, and delete the object.
      - May contain C({id}).
      - Must be relative; absolute and cross-origin URLs are rejected.
    type: str
    required: true
  id:
    description:
      - Object identity substituted for C({id}) in I(path) and I(create_path).
    type: str
  create_path:
    description:
      - API path used to create the object.
      - Defaults to I(path).
    type: str
  payload:
    description:
      - Desired request body.
      - Required when I(state=present).
    type: dict
  query:
    description:
      - Query parameters included in every operation.
    type: dict
    default: {}
  get_method:
    description: HTTP method used to read current state.
    type: str
    choices: [GET, POST]
    default: GET
  create_method:
    description: HTTP method used to create the object.
    type: str
    choices: [POST, PUT, PATCH]
    default: PUT
  update_method:
    description: HTTP method used to update the object.
    type: str
    choices: [POST, PUT, PATCH]
    default: PUT
  delete_method:
    description: HTTP method used to delete the object.
    type: str
    choices: [DELETE, POST]
    default: DELETE
  get_success_codes:
    description: HTTP status codes accepted when reading the object.
    type: list
    elements: int
    default: [200]
  create_success_codes:
    description: HTTP status codes accepted when creating the object.
    type: list
    elements: int
    default: [200, 201, 202]
  update_success_codes:
    description: HTTP status codes accepted when updating the object.
    type: list
    elements: int
    default: [200, 201, 202]
  delete_success_codes:
    description: HTTP status codes accepted when deleting the object.
    type: list
    elements: int
    default: [200, 202, 204]
  not_found_codes:
    description: HTTP status codes that mean the object does not exist.
    type: list
    elements: int
    default: [404]
  response_path:
    description:
      - Dot-separated path to the managed object in API responses.
      - The extracted value is used for comparison and returned as the managed object.
    type: str
  compare_fields:
    description:
      - Dot-separated fields to compare.
      - By default, all fields supplied in I(payload) are compared.
    type: list
    elements: str
    default: []
  ignore_fields:
    description: Dot-separated fields excluded from comparison and diff.
    type: list
    elements: str
    default: []
  sensitive_fields:
    description: Dot-separated fields redacted from every object, diff, and failure response.
    type: list
    elements: str
    default: []
  unordered_lists:
    description: Sort lists by their canonical JSON representation before comparison.
    type: bool
    default: false
  state:
    description: Whether the object should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Prefer a typed module when one is available.
  - Unknown server-managed fields are ignored unless selected with I(compare_fields).
"""

EXAMPLES = r"""
- name: Manage a saved object using environment authentication
  zupersero.kibana.kibana_object:
    path: /api/saved_objects/index-pattern/{id}
    id: logs-view
    create_method: POST
    update_method: PUT
    payload:
      attributes:
        title: logs-*
        timeFieldName: '@timestamp'
    state: present

- name: Remove the saved object
  zupersero.kibana.kibana_object:
    path: /api/saved_objects/index-pattern/{id}
    id: logs-view
    state: absent
"""

RETURN = r"""
object:
  description: Managed object extracted from the most relevant API response.
  returned: always
  type: dict
status:
  description: HTTP status of the last operation.
  returned: always
  type: int
diff:
  description: Sanitized before and after state.
  returned: when diff mode is enabled and a change is required
  type: dict
"""

from typing import Any  # noqa: E402
from urllib.parse import quote  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


def _render_path(module: AnsibleModule, path: str) -> str:
    if "{id}" not in path:
        return path
    identity = module.params.get("id")
    if identity is None:
        module.fail_json(msg="`id` is required when an API path contains `{id}`")
    return path.replace("{id}", quote(identity, safe=""))


def _extract(response: Any, response_path: str | None) -> Any:
    return kibana.extract_value(response, response_path) if response_path else response


def _fail_operation(
    module: AnsibleModule,
    operation: str,
    path: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=f"Kibana object {operation} failed for {path} with HTTP {status}",
        status=status,
        response=kibana.sanitize(response, module.params["sensitive_fields"]),
    )


def _exit_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    """Return an object result with configured sensitive fields redacted."""
    sensitive_fields = module.params["sensitive_fields"]
    if "object" in result:
        result["object"] = kibana.sanitize(result["object"], sensitive_fields)
    if "diff" in result:
        result["diff"] = {
            "before": kibana.sanitize(
                result["diff"].get("before"), sensitive_fields
            ),
            "after": kibana.sanitize(
                result["diff"].get("after"), sensitive_fields
            ),
        }
    module.exit_json(**result)


def run_module(
    module: AnsibleModule, client: kibana.KibanaClient | None = None
) -> None:
    """Reconcile an arbitrary Kibana object."""
    client = client or kibana.KibanaClient(module)
    item_path = client.space_path(_render_path(module, module.params["path"]))
    create_path = client.space_path(
        _render_path(module, module.params.get("create_path") or module.params["path"])
    )
    query = module.params.get("query")
    status, current_response = client.request(
        module.params["get_method"],
        item_path,
        query=query,
        sensitive_fields=module.params["sensitive_fields"],
    )
    not_found = status in module.params["not_found_codes"]
    if not not_found and status not in module.params["get_success_codes"]:
        _fail_operation(module, "read", item_path, status, current_response)

    current = None if not_found else _extract(
        current_response, module.params.get("response_path")
    )
    state = module.params["state"]
    result = {"changed": False, "object": current, "status": status}

    if state == "absent":
        if not_found:
            _exit_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _exit_result(module, result)
        status, response = client.request(
            module.params["delete_method"],
            item_path,
            query=query,
            sensitive_fields=module.params["sensitive_fields"],
        )
        if status not in module.params["delete_success_codes"]:
            _fail_operation(module, "delete", item_path, status, response)
        result.update(status=status, object=None)
        _exit_result(module, result)

    desired = module.params["payload"]
    if not_found:
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": {}, "after": desired}
        if module.check_mode:
            result["object"] = desired
            _exit_result(module, result)
        status, response = client.request(
            module.params["create_method"],
            create_path,
            data=desired,
            query=query,
            sensitive_fields=module.params["sensitive_fields"],
        )
        if status not in module.params["create_success_codes"]:
            _fail_operation(module, "create", create_path, status, response)
        result.update(
            status=status,
            object=_extract(response, module.params.get("response_path")),
        )
        _exit_result(module, result)

    changed, diff = kibana.comparison_diff(
        current,
        desired,
        compare_fields=module.params.get("compare_fields"),
        ignore_fields=module.params["ignore_fields"],
        sensitive_fields=module.params["sensitive_fields"],
        unordered_lists=module.params["unordered_lists"],
    )
    if not changed:
        _exit_result(module, result)

    result["changed"] = True
    if module._diff:
        result["diff"] = diff
    if module.check_mode:
        result["object"] = desired
        _exit_result(module, result)
    status, response = client.request(
        module.params["update_method"],
        item_path,
        data=desired,
        query=query,
        sensitive_fields=module.params["sensitive_fields"],
    )
    if status not in module.params["update_success_codes"]:
        _fail_operation(module, "update", item_path, status, response)
    result.update(
        status=status,
        object=_extract(response, module.params.get("response_path")),
    )
    _exit_result(module, result)


def main() -> None:
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        path=dict(type="str", required=True),
        id=dict(type="str"),
        create_path=dict(type="str"),
        payload=dict(type="dict"),
        query=dict(type="dict", default={}),
        get_method=dict(type="str", choices=["GET", "POST"], default="GET"),
        create_method=dict(
            type="str", choices=["POST", "PUT", "PATCH"], default="PUT"
        ),
        update_method=dict(
            type="str", choices=["POST", "PUT", "PATCH"], default="PUT"
        ),
        delete_method=dict(type="str", choices=["DELETE", "POST"], default="DELETE"),
        get_success_codes=dict(type="list", elements="int", default=[200]),
        create_success_codes=dict(
            type="list", elements="int", default=[200, 201, 202]
        ),
        update_success_codes=dict(
            type="list", elements="int", default=[200, 201, 202]
        ),
        delete_success_codes=dict(
            type="list", elements="int", default=[200, 202, 204]
        ),
        not_found_codes=dict(type="list", elements="int", default=[404]),
        response_path=dict(type="str"),
        compare_fields=dict(type="list", elements="str", default=[]),
        ignore_fields=dict(type="list", elements="str", default=[]),
        sensitive_fields=dict(type="list", elements="str", default=[]),
        unordered_lists=dict(type="bool", default=False),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[["state", "present", ["payload"]]],
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )

    run_module(module)


if __name__ == "__main__":
    main()
