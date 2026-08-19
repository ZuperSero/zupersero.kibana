# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=unsupported-binary-operation

"""Manage an installed Kibana Fleet integration package."""

DOCUMENTATION = r"""
---
module: fleet_package
short_description: Manage an installed Kibana Fleet package
description:
  - Installs, upgrades, updates, and uninstalls one package from the Fleet package registry.
  - Installation is reconciled against Kibana's installed-package list and is idempotent.
  - Supports exact package versions, prerelease packages, force operations, check mode, and diff mode.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  name:
    description: Registry package name, for example C(system) or C(elastic_agent).
    type: str
    required: true
  package_version:
    description: Exact package version to install or upgrade to. Omit to use Kibana's current registry version.
    type: str
    aliases: [version]
  prerelease:
    description: Include prerelease package versions when resolving an omitted version.
    type: bool
    default: false
  force:
    description: Force package actions when package policies or constraints would otherwise prevent them.
    type: bool
    default: false
  ignore_constraints:
    description: Ignore package dependency constraints during installation.
    type: bool
    default: false
  ignore_mapping_update_errors:
    description: Continue installation when Elasticsearch mapping updates fail.
    type: bool
    default: false
  skip_data_stream_rollover:
    description: Skip data-stream rollover during package installation.
    type: bool
    default: false
  keep_policies_up_to_date:
    description: Update existing package policies when upgrading this package.
    type: bool
    default: false
  sensitive_fields:
    description: Dot-separated response fields to redact from output and diffs.
    type: list
    elements: str
    default: []
  state:
    description: Whether the package should be installed or absent.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Fleet package installation requires integrations and Fleet agent-policy privileges and a configured package registry.
  - Package actions may be slow because Kibana installs assets and updates Elasticsearch mappings.
  - Uninstalling a package can remove package assets and invalidate package policies; use I(force=true) deliberately.
  - I(package_version) is an exact version, not a range expression.
"""

EXAMPLES = r"""
- name: Install the system integration
  zupersero.kibana.fleet_package:
    name: system

- name: Install a pinned package version and allow prerelease resolution
  zupersero.kibana.fleet_package:
    name: nginx
    package_version: 1.26.0
    prerelease: true

- name: Upgrade a package and its existing policies
  zupersero.kibana.fleet_package:
    name: system
    package_version: 1.20.0
    keep_policies_up_to_date: true

- name: Uninstall a package
  zupersero.kibana.fleet_package:
    name: system
    state: absent
    force: true
"""

RETURN = r"""
fleet_package:
  description: Installed package state, or null after uninstall.
  returned: always
  type: dict
status:
  description: HTTP status code of the last API operation.
  returned: always
  type: int
operation:
  description: Action performed, such as install, update, or uninstall.
  returned: always
  type: str
diff:
  description: Sanitized before and after installed state.
  returned: when diff mode is enabled and a change is required
  type: dict
"""

from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
ACTION_SUCCESS_CODES = (200, 201, 202, 204)
NOT_FOUND_CODES = (404,)
MANAGED_FIELDS = ("name", "version")


def fleet_package_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete typed Fleet-package argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        name=dict(type="str", required=True),
        package_version=dict(type="str", aliases=["version"]),
        prerelease=dict(type="bool", default=False),
        force=dict(type="bool", default=False),
        ignore_constraints=dict(type="bool", default=False),
        ignore_mapping_update_errors=dict(type="bool", default=False),
        skip_data_stream_rollover=dict(type="bool", default=False),
        keep_policies_up_to_date=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _error(module: AnsibleModule, operation: str, status: int, response: Any) -> None:
    module.fail_json(
        msg=f"Kibana Fleet package {operation} failed for `{module.params['name']}` with HTTP {status}",
        status=status,
        response=kibana.sanitize(response, module.params.get("sensitive_fields", [])),
    )


def _items(response: Any) -> list[Mapping[str, Any]] | None:
    if not isinstance(response, Mapping):
        return None
    value = response.get("items")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return None


def _installed(module: AnsibleModule, service: Any) -> tuple[int, dict | None]:
    status, response = service.list_installed()
    if status not in READ_SUCCESS_CODES:
        _error(module, "installed-package lookup", status, response)
    items = _items(response)
    if items is None:
        module.fail_json(
            msg="Kibana Fleet installed-package lookup returned a malformed response",
            status=status,
            response=kibana.sanitize(response),
        )
    matches = [item for item in items if item.get("name") == module.params["name"]]
    if len(matches) > 1:
        module.fail_json(msg=f"Kibana returned duplicate installed packages named `{module.params['name']}`")
    return (status, dict(matches[0])) if matches else (status, None)


def _safe_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    fields = module.params.get("sensitive_fields", [])
    if "fleet_package" in result:
        result["fleet_package"] = kibana.sanitize(result["fleet_package"], fields)
    if "diff" in result:
        result["diff"] = kibana.sanitize(result["diff"], fields)
    module.exit_json(**result)


def run_module(module: AnsibleModule, client: kibana.KibanaClient | None = None) -> None:
    """Reconcile one installed Fleet package."""
    client = client or kibana.KibanaClient(module)
    service = client.epm
    status, current = _installed(module, service)
    result: dict[str, Any] = {
        "changed": False,
        "fleet_package": current,
        "status": status,
        "operation": "none",
    }
    state = module.params["state"]
    requested = module.params.get("package_version")

    if state == "absent":
        if current is None:
            _safe_result(module, result)
        result.update(changed=True, operation="uninstall")
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _safe_result(module, result)
        status, response = service.delete(
            module.params["name"],
            package_version=current.get("version"),
            force=module.params["force"],
        )
        if status not in ACTION_SUCCESS_CODES and status not in NOT_FOUND_CODES:
            _error(module, "uninstall", status, response)
        result.update(status=status, fleet_package=None)
        _safe_result(module, result)

    installed_version = current.get("version") if current else None
    needs_action = current is None or (requested is not None and requested != installed_version)
    if current is not None and requested is None and not module.params["force"]:
        needs_action = False
    if not needs_action:
        _safe_result(module, result)

    result["changed"] = True
    result["operation"] = "install" if current is None else "update"
    preview = dict(current or {"name": module.params["name"]})
    if requested is not None:
        preview["version"] = requested
    if module._diff:
        result["diff"] = {"before": current or {}, "after": preview}
    result["fleet_package"] = preview
    if module.check_mode:
        _safe_result(module, result)

    if current is None:
        status, response = service.install(
            module.params["name"],
            package_version=requested,
            prerelease=module.params["prerelease"],
            ignore_mapping_update_errors=module.params["ignore_mapping_update_errors"],
            skip_data_stream_rollover=module.params["skip_data_stream_rollover"],
            force=module.params["force"],
            ignore_constraints=module.params["ignore_constraints"],
        )
        operation = "install"
    else:
        status, response = service.update(
            module.params["name"],
            package_version=requested,
            keep_policies_up_to_date=module.params["keep_policies_up_to_date"],
        )
        operation = "update"
    if status not in ACTION_SUCCESS_CODES:
        _error(module, operation, status, response)
    result.update(status=status, operation=operation, fleet_package=response)
    _safe_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=fleet_package_argument_spec(),
        supports_check_mode=True,
        required_if=kibana.kibana_required_if(),
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
