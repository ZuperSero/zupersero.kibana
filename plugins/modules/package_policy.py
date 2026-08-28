# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=unsupported-binary-operation

"""Manage one Fleet integration (package) policy."""

READ_SUCCESS_CODES = (200,)
CREATE_SUCCESS_CODES = (200, 201)
UPDATE_SUCCESS_CODES = (200,)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
MANAGED_FIELDS = (
    "name",
    "namespace",
    "description",
    "package",
    "policy_id",
    "inputs",
    "vars",
)


DOCUMENTATION = r"""
---
module: package_policy
short_description: Manage a Kibana Fleet integration policy
description:
  - Creates, updates, reads, and deletes one Fleet package policy.
  - Package policies attach an installed integration package to an agent policy.
  - When I(id) is omitted, an exact unique I(name) (and I(policy_id), when supplied) is used to find the generated Kibana identifier.
  - Omitted fields are preserved during updates. Use I(replace=true) to clear omitted I(inputs) and I(vars).
  - Supports check mode, diff mode, idempotency, and sanitized failures.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id:
    description: Server-generated package-policy identifier.
    type: str
  name:
    description:
      - Display name for the integration policy.
      - Required when creating a policy, or when finding one without I(id).
    type: str
  namespace:
    description: Fleet data namespace for the integration policy.
    type: str
    default: default
  package:
    description:
      - Integration package name, such as C(system) or C(elasticsearch).
      - The package must be installed in Kibana before this policy is created or changed.
    type: str
  package_version:
    description:
      - Installed integration package version.
      - On creation, omit it to use the installed version when exactly one version is installed.
      - On update, omission preserves the current version.
    type: str
  policy_id:
    description:
      - Identifier of the Fleet agent policy to which this integration is attached.
      - The agent policy must already exist.
    type: str
  description:
    description: Optional integration policy description. Use an empty string to clear it.
    type: str
  inputs:
    description:
      - Package-specific input configuration.
      - This may contain credentials or endpoint secrets and is never returned unsanitized.
      - Omit during an update to preserve current inputs; use an empty dictionary to clear them.
    type: dict
  vars:
    description:
      - Package-specific variables.
      - This may contain credentials or endpoint secrets and is never returned unsanitized.
      - Omit during an update to preserve current variables; use an empty dictionary to clear them.
    type: dict
  replace:
    description: Treat omitted I(inputs) and I(vars) as empty dictionaries during updates.
    type: bool
    default: false
  force:
    description: Force deletion when Kibana reports that the policy is in use.
    type: bool
    default: false
  sensitive_fields:
    description: Dot-separated response fields to redact in output, diffs, and failures.
    type: list
    elements: str
    default: []
  state:
    description: Whether the package policy should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Fleet package-policy APIs require Fleet privileges and an installed package.
  - Package policies are not space-scoped; I(space) is retained as a common connection option.
"""

EXAMPLES = r"""
- name: Configure the system integration on the default agent policy
  zupersero.kibana.package_policy:
    name: Linux system metrics
    namespace: default
    package: system
    package_version: 1.49.0
    policy_id: fleet-agent-policy
    inputs:
      system/metrics:
        enabled: true
        streams:
          system.cpu:
            enabled: true

- name: Update only package variables and preserve inputs
  zupersero.kibana.package_policy:
    id: generated-package-policy-id
    vars:
      custom_variable: example

- name: Delete an integration policy
  zupersero.kibana.package_policy:
    name: Linux system metrics
    policy_id: fleet-agent-policy
    state: absent
"""

RETURN = r"""
package_policy:
  description: Current or resulting Fleet package policy, with sensitive values redacted.
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


def package_policy_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete package-policy argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        id=dict(type="str"),
        name=dict(type="str"),
        namespace=dict(type="str", default="default"),
        package=dict(type="str"),
        package_version=dict(type="str"),
        policy_id=dict(type="str"),
        description=dict(type="str"),
        inputs=dict(type="dict", no_log=True),
        vars=dict(type="dict", no_log=True),
        replace=dict(type="bool", default=False),
        force=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _extract_policy(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, Mapping):
        return None
    for key in ("item", "package_policy", "packagePolicy"):
        item = response.get(key)
        if isinstance(item, Mapping):
            return dict(item)
    return dict(response)


def _list_items(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, Mapping):
        return []
    for key in ("items", "package_policies", "packagePolicies"):
        values = response.get(key)
        if isinstance(values, list):
            return [dict(value) for value in values if isinstance(value, Mapping)]
    return []


def _installed_items(response: Any) -> list[dict[str, Any]]:
    """Normalize EPM installed-package responses across Stack versions."""
    if isinstance(response, list):
        values = response
    elif isinstance(response, Mapping):
        values = response.get("items", response.get("packages", response.get("response", [])))
    else:
        values = []
    return [dict(value) for value in values if isinstance(value, Mapping)]


def _package_name(item: Mapping[str, Any]) -> str | None:
    package = item.get("package")
    if isinstance(package, Mapping):
        value = package.get("name")
        if isinstance(value, str):
            return value
    value = item.get("name")
    return value if isinstance(value, str) else None


def _package_version(item: Mapping[str, Any]) -> str | None:
    package = item.get("package")
    if isinstance(package, Mapping):
        value = package.get("version")
        if isinstance(value, str):
            return value
    value = item.get("version")
    return value if isinstance(value, str) else None


def _validate_response(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> dict[str, Any]:
    result = _extract_policy(response)
    if result is None or not isinstance(result.get("id"), str):
        module.fail_json(
            msg=f"Kibana Fleet package policy {operation} returned a malformed response",
            status=status,
            response=kibana.sanitize(response, module.params["sensitive_fields"]),
        )
    return result


def _fail_operation(
    module: AnsibleModule, operation: str, status: int, response: Any
) -> None:
    module.fail_json(
        msg=f"Kibana Fleet package policy {operation} failed with HTTP {status}",
        status=status,
        response=kibana.sanitize(response, module.params["sensitive_fields"]),
    )


def _find_existing(module: AnsibleModule, service: Any) -> dict[str, Any] | None:
    policy_id = module.params.get("id")
    if policy_id:
        status, response = service.get(policy_id)
        if status in READ_SUCCESS_CODES:
            return _validate_response(module, "read", status, response)
        if status in NOT_FOUND_CODES:
            return None
        _fail_operation(module, "read", status, response)

    name = module.params.get("name")
    if not name:
        return None
    status, response = service.list()
    if status not in READ_SUCCESS_CODES:
        _fail_operation(module, "list", status, response)
    candidates = [item for item in _list_items(response) if item.get("name") == name]
    policy_id = module.params.get("policy_id")
    if policy_id:
        candidates = [item for item in candidates if item.get("policy_id") == policy_id]
    if len(candidates) > 1:
        module.fail_json(
            msg=(
                f"More than one Fleet package policy matches exact name `{name}`; "
                "use `id` or also specify a unique `policy_id`"
            )
        )
    return candidates[0] if candidates else None


def _validate_create_options(module: AnsibleModule) -> None:
    missing = [
        name
        for name in ("name", "package", "policy_id")
        if not module.params.get(name)
    ]
    if missing:
        module.fail_json(
            msg="Creating a Fleet package policy requires: "
            + ", ".join(f"`{name}`" for name in missing)
        )


def _validate_agent_policy(module: AnsibleModule, client: Any, policy_id: str) -> None:
    status, response = client.agent_policies.get(policy_id)
    if status not in READ_SUCCESS_CODES:
        if status in NOT_FOUND_CODES:
            module.fail_json(msg=f"Fleet agent policy `{policy_id}` does not exist", status=status)
        _fail_operation(module, "agent-policy validation", status, response)


def _resolve_installed_package(
    module: AnsibleModule,
    client: Any,
    package_name: str,
    requested_version: str | None,
) -> str:
    status, response = client.epm.list_installed()
    if status not in READ_SUCCESS_CODES:
        _fail_operation(module, "installed-package validation", status, response)
    candidates = [
        item
        for item in _installed_items(response)
        if _package_name(item) == package_name
    ]
    if requested_version:
        candidates = [item for item in candidates if _package_version(item) == requested_version]
    if not candidates:
        version_text = f" version `{requested_version}`" if requested_version else ""
        module.fail_json(
            msg=f"Fleet package `{package_name}`{version_text} is not installed in Kibana",
            status=status,
            response=kibana.sanitize(response, module.params["sensitive_fields"]),
        )
    versions = sorted(
        (version for version in (_package_version(item) for item in candidates) if version),
        reverse=True,
    )
    if not versions:
        module.fail_json(msg=f"Installed Fleet package `{package_name}` has no version")
    return versions[0]


def _desired(module: AnsibleModule, current: Mapping[str, Any] | None) -> dict[str, Any]:
    params = module.params
    package_name = params.get("package")
    package_version = params.get("package_version")
    if package_name is None and current:
        package_name = _package_name(current.get("package", {}))
    if package_version is None and current:
        package_version = _package_version(current.get("package", {}))
    desired: dict[str, Any] = {}
    for field in ("name", "namespace", "description", "policy_id"):
        value = params.get(field)
        if value is not None:
            desired[field] = value
    if package_name is not None:
        if package_version is None:
            module.fail_json(msg="`package_version` is required when `package` is supplied")
        desired["package"] = {"name": package_name, "version": package_version}
    for field in ("inputs", "vars"):
        value = params.get(field)
        if value is not None:
            desired[field] = value
    if params.get("replace"):
        desired.setdefault("inputs", {})
        desired.setdefault("vars", {})
    return desired


def _merge_mapping(current: Any, desired: Any) -> Any:
    if isinstance(current, Mapping) and isinstance(desired, Mapping) and desired:
        result = dict(current)
        for key, value in desired.items():
            result[key] = _merge_mapping(current.get(key), value)
        return result
    return desired


def _update_payload(current: Mapping[str, Any], desired: Mapping[str, Any]) -> dict[str, Any]:
    payload = {field: current[field] for field in MANAGED_FIELDS if field in current}
    for field in ("inputs", "vars"):
        if field in desired and desired[field]:
            payload[field] = _merge_mapping(current.get(field, {}), desired[field])
    payload.update({field: value for field, value in desired.items() if field not in ("inputs", "vars")})
    for field in ("inputs", "vars"):
        if field in desired and not desired[field]:
            payload[field] = {}
    return payload


def _diff(
    current: Mapping[str, Any] | None,
    desired: Mapping[str, Any],
    sensitive_fields: list[str],
) -> tuple[bool, dict[str, Any]]:
    before = dict(current or {})
    projected = dict(before)
    for field, value in desired.items():
        if field == "package" and isinstance(value, Mapping):
            projected[field] = _merge_mapping(before.get(field, {}), value)
        elif field in ("inputs", "vars") and value and isinstance(value, Mapping):
            projected[field] = _merge_mapping(before.get(field, {}), value)
        else:
            projected[field] = value
    changed = kibana.normalize_for_comparison(projected) != kibana.normalize_for_comparison(before)
    return changed, {
        "before": kibana.sanitize(before, sensitive_fields=sensitive_fields),
        "after": kibana.sanitize(projected, sensitive_fields=sensitive_fields),
    }


def _finish(module: AnsibleModule, result: dict[str, Any]) -> None:
    if "package_policy" in result:
        result["package_policy"] = kibana.sanitize(
            result["package_policy"], sensitive_fields=module.params["sensitive_fields"]
        )
    if "diff" in result:
        result["diff"] = kibana.sanitize(
            result["diff"], sensitive_fields=module.params["sensitive_fields"]
        )
    module.exit_json(**result)


def run_module(module: AnsibleModule, client: Any | None = None) -> None:
    client = client or kibana.KibanaClient(module)
    service = client.package_policies
    current = _find_existing(module, service)
    result: dict[str, Any] = {"changed": False, "package_policy": current, "status": 200}

    if module.params["state"] == "absent":
        if current is None:
            _finish(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _finish(module, result)
        status, response = service.delete(module.params.get("id") or current["id"], module.params["force"])
        if status not in DELETE_SUCCESS_CODES:
            _fail_operation(module, "delete", status, response)
        result.update(status=status, package_policy=None)
        _finish(module, result)

    if current is None:
        _validate_create_options(module)
        _validate_agent_policy(module, client, module.params["policy_id"])
        version = _resolve_installed_package(
            module, client, module.params["package"], module.params.get("package_version")
        )
        params = dict(module.params)
        params["package_version"] = version
        module.params.update(params)
        desired = _desired(module, None)
        payload = dict(desired)
        payload.setdefault("inputs", {})
        payload.setdefault("vars", {})
        preview = {"id": module.params.get("id") or "", **payload}
        result.update(changed=True, package_policy=preview, status=0)
        if module._diff:
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _finish(module, result)
        status, response = service.create(payload)
        if status not in CREATE_SUCCESS_CODES:
            _fail_operation(module, "create", status, response)
        result.update(status=status, package_policy=_validate_response(module, "create", status, response))
        _finish(module, result)

    policy_id = module.params.get("policy_id")
    if policy_id:
        _validate_agent_policy(module, client, policy_id)
    package_name = module.params.get("package")
    if package_name:
        _resolve_installed_package(module, client, package_name, module.params.get("package_version"))
    desired = _desired(module, current)
    changed, diff = _diff(current, desired, module.params["sensitive_fields"])
    if not changed:
        _finish(module, result)
    result["changed"] = True
    if module._diff:
        result["diff"] = diff
    if module.check_mode:
        result["package_policy"] = _merge_mapping(current, desired)
        _finish(module, result)
    payload = _update_payload(current, desired)
    status, response = service.update(current["id"], payload)
    if status not in UPDATE_SUCCESS_CODES:
        _fail_operation(module, "update", status, response)
    result.update(status=status, package_policy=_validate_response(module, "update", status, response))
    _finish(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=package_policy_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
