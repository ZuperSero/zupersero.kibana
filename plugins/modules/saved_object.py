# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Manage one Kibana saved object."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: saved_object
short_description: Manage a Kibana saved object
description:
  - Creates, reads, updates, and deletes a Kibana saved object with an explicit identifier.
  - Reads current state before mutation and preserves fields not supplied in I(attributes).
  - Supports Kibana spaces, check mode, diff mode, and idempotent deletion.
  - The underlying single-object saved objects API is deprecated by Kibana and may be removed in a future Elastic Stack release.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  type:
    description:
      - Saved object type, such as C(index-pattern), C(dashboard), or C(visualization).
    type: str
    required: true
  id:
    description:
      - Unique saved object identifier.
    type: str
    required: true
  attributes:
    description:
      - Saved object attributes to create or update.
      - Required when I(state=present).
      - Existing attribute keys omitted from this dictionary are preserved and ignored for idempotency comparison.
    type: dict
  references:
    description:
      - References from this saved object to other saved objects.
      - When omitted, existing references are preserved during updates.
    type: list
    elements: dict
    suboptions:
      id:
        description: Identifier of the referenced saved object.
        type: str
        required: true
      type:
        description: Type of the referenced saved object.
        type: str
        required: true
      name:
        description: Name used by the saved object attribute that holds the reference.
        type: str
        required: true
  force_delete:
    description:
      - Delete an object that exists in multiple namespaces.
      - Kibana also deletes legacy URL aliases that reference the object when this is enabled.
    type: bool
    default: false
  sensitive_fields:
    description:
      - Dot-separated saved-object fields to redact from output, diffs, and API failures.
      - For example, C(attributes.private_value).
    type: list
    elements: str
    default: []
  state:
    description: Whether the saved object should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - The I(space) option selects the space containing the object. Use C(default) for the default space.
  - The module manages only supplied attribute keys, and manages the complete references list only when I(references) is supplied.
"""

EXAMPLES = r"""
- name: Create an index-pattern saved object
  zupersero.kibana.saved_object:
    type: index-pattern
    id: application-logs
    attributes:
      title: "application-logs-*"
      timeFieldName: "@timestamp"
    state: present

- name: Update a saved object in a non-default space
  zupersero.kibana.saved_object:
    space: operations
    type: index-pattern
    id: application-logs
    attributes:
      title: "application-metrics-*"
      timeFieldName: "@timestamp"

- name: Delete a saved object
  zupersero.kibana.saved_object:
    type: index-pattern
    id: application-logs
    state: absent

- name: Use environment-based authentication
  zupersero.kibana.saved_object:
    type: index-pattern
    id: application-logs
    attributes:
      title: "application-logs-*"
  environment:
    KIBANA_URL: https://kibana.example.com
    KIBANA_API_KEY: your-encoded-api-key
"""

RETURN = r"""
saved_object:
  description:
    - The current or resulting saved object.
    - C(null) after deletion or when the requested absent object does not exist.
  returned: always
  type: dict
status:
  description: HTTP status code of the last API operation.
  returned: always
  type: int
diff:
  description: Sanitized before and after managed state.
  returned: when diff mode is enabled and a change is required
  type: dict
"""

from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
CREATE_SUCCESS_CODES = (200, 201)
UPDATE_SUCCESS_CODES = (200,)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
SAVED_OBJECT_REQUIRED_IF = [["state", "present", ["attributes"]]]


def saved_object_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete typed saved-object argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        type=dict(type="str", required=True),
        id=dict(type="str", required=True),
        attributes=dict(type="dict"),
        references=dict(
            type="list",
            elements="dict",
            options=dict(
                id=dict(type="str", required=True),
                type=dict(type="str", required=True),
                name=dict(type="str", required=True),
            ),
        ),
        force_delete=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def build_payload(params: Mapping[str, Any]) -> dict[str, Any]:
    """Build a saved objects API payload from managed module parameters."""
    payload = {"attributes": params["attributes"]}
    if params.get("references") is not None:
        payload["references"] = params["references"]
    return payload


def _merge_preview(current: Any, desired: Any) -> Any:
    """Overlay desired state while retaining server fields for check-mode output."""
    if isinstance(current, Mapping) and isinstance(desired, Mapping):
        result = dict(current)
        for key, value in desired.items():
            result[key] = _merge_preview(current.get(key), value)
        return result
    return desired


def build_update_payload(
    current: Mapping[str, Any],
    desired: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the full replacement body required by Kibana's update endpoint."""
    payload = {
        "attributes": _merge_preview(
            current.get("attributes", {}),
            desired["attributes"],
        )
    }
    if "references" in desired:
        payload["references"] = desired["references"]
    elif isinstance(current.get("references"), list):
        payload["references"] = current["references"]
    return payload


def _sanitize_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    sensitive_fields = module.params["sensitive_fields"]
    if "saved_object" in result:
        result["saved_object"] = kibana.sanitize(
            result["saved_object"],
            sensitive_fields=sensitive_fields,
        )
    if "diff" in result:
        result["diff"] = kibana.sanitize(
            result["diff"],
            sensitive_fields=sensitive_fields,
        )
    module.exit_json(**result)


def _fail_operation(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=(
            f"Kibana saved object {operation} failed for "
            f"{module.params['type']}/{module.params['id']} with HTTP {status}"
        ),
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params["sensitive_fields"],
        ),
    )


def _validated_object(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> dict[str, Any]:
    """Validate the minimum response shape required by the public return contract."""
    if (
        not isinstance(response, Mapping)
        or not isinstance(response.get("attributes"), Mapping)
        or not isinstance(response.get("id"), str)
        or not isinstance(response.get("type"), str)
    ):
        module.fail_json(
            msg=(
                f"Kibana saved object {operation} returned a malformed "
                f"response for {module.params['type']}/{module.params['id']}"
            ),
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )
    return dict(response)


def _preview_created(
    params: Mapping[str, Any],
    desired: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": params["id"],
        "type": params["type"],
        **desired,
    }


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Reconcile one typed Kibana saved object."""
    client = client or kibana.KibanaClient(module)
    service = client.saved_objects
    object_type = module.params["type"]
    object_id = module.params["id"]
    sensitive_fields = module.params["sensitive_fields"]

    status, response = service.get(
        object_type,
        object_id,
        sensitive_fields=sensitive_fields,
    )
    if status in READ_SUCCESS_CODES:
        current = _validated_object(module, "read", status, response)
    elif status in NOT_FOUND_CODES:
        current = None
    else:
        _fail_operation(module, "read", status, response)

    result = {
        "changed": False,
        "saved_object": current,
        "status": status,
    }

    if module.params["state"] == "absent":
        if current is None:
            _sanitize_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.delete(
            object_type,
            object_id,
            force=module.params["force_delete"],
            sensitive_fields=sensitive_fields,
        )
        if status not in DELETE_SUCCESS_CODES:
            _fail_operation(module, "delete", status, response)
        result.update(status=status, saved_object=None)
        _sanitize_result(module, result)

    desired = build_payload(module.params)
    if current is None:
        preview = _preview_created(module.params, desired)
        result.update(changed=True, saved_object=preview)
        if module._diff:
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.create(
            object_type,
            object_id,
            desired,
            sensitive_fields=sensitive_fields,
        )
        if status not in CREATE_SUCCESS_CODES:
            _fail_operation(module, "create", status, response)
        result.update(
            status=status,
            saved_object=_validated_object(module, "create", status, response),
        )
        _sanitize_result(module, result)

    changed, diff = kibana.comparison_diff(
        current,
        desired,
        sensitive_fields=module.params["sensitive_fields"],
    )
    if not changed:
        _sanitize_result(module, result)

    result["changed"] = True
    if module._diff:
        result["diff"] = diff
    if module.check_mode:
        result["saved_object"] = _merge_preview(current, desired)
        _sanitize_result(module, result)

    update_payload = build_update_payload(current, desired)
    status, response = service.update(
        object_type,
        object_id,
        update_payload,
        sensitive_fields=sensitive_fields,
    )
    if status not in UPDATE_SUCCESS_CODES:
        _fail_operation(module, "update", status, response)
    result.update(
        status=status,
        saved_object=_validated_object(module, "update", status, response),
    )
    _sanitize_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=saved_object_argument_spec(),
        supports_check_mode=True,
        required_if=SAVED_OBJECT_REQUIRED_IF,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
