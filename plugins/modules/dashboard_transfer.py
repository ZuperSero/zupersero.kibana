# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transfer a Kibana dashboard artifact between spaces."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: dashboard_transfer
short_description: Transfer a Kibana dashboard between spaces
description:
  - Exports one dashboard and, by default, its complete dependency graph from a source space.
  - Imports the exact opaque NDJSON export into another space using Kibana's supported saved objects APIs.
  - This is an explicit workflow action, not an idempotent CRUD module.
  - A successfully accepted import reports I(changed=true), including an overwrite of equivalent objects.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  dashboard_id:
    description: Identifier of the dashboard to transfer.
    type: str
    required: true
  target_space:
    description: Kibana space into which the dashboard artifact is imported.
    type: str
    required: true
  include_references_deep:
    description:
      - Whether to include the dashboard's complete saved-object dependency graph.
      - Keep enabled for a portable dashboard artifact.
    type: bool
    default: true
  fail_on_missing_references:
    description:
      - Fail before import when Kibana reports missing dashboard dependencies.
      - Disable only when intentionally transferring an incomplete artifact.
    type: bool
    default: true
  overwrite:
    description:
      - Overwrite conflicting objects in the target space.
      - Mutually exclusive with I(create_new_copies).
    type: bool
    default: false
  create_new_copies:
    description:
      - Regenerate object identifiers and reset each object's origin during import.
      - Mutually exclusive with I(overwrite) and I(compatibility_mode).
    type: bool
    default: false
  compatibility_mode:
    description:
      - Apply Kibana compatibility adjustments during import.
      - Use only when a cross-version artifact encounters compatibility problems.
      - Mutually exclusive with I(create_new_copies).
    type: bool
    default: false
  return_artifact:
    description:
      - Return the exact opaque NDJSON artifact in I(artifact).
      - Disabled by default because dashboard artifacts can contain sensitive data.
    type: bool
    default: false
  sensitive_fields:
    description:
      - Dot-separated fields redacted from parsed objects, results, and API failures.
      - This never rewrites the opaque NDJSON passed between Kibana APIs.
    type: list
    elements: str
    default: []
notes:
  - The common I(space) option selects the source space; I(target_space) selects the destination.
  - The source and target spaces must differ.
  - Kibana can remap identifiers during import even when I(create_new_copies=false).
    Use I(dashboard_id) and each result's C(destinationId) from the returned import summary.
  - In check mode, the source artifact is exported and validated, no import request is sent, and the module predicts I(changed=true).
  - The artifact is passed byte-for-byte from export to import. Exported saved objects are not backward compatible with older Kibana versions.
  - Set task-level C(no_log=true) when I(return_artifact=true) and the dashboard may contain sensitive configuration.
"""

EXAMPLES = r"""
- name: Transfer a dashboard and all dependencies into operations
  zupersero.kibana.dashboard_transfer:
    space: default
    target_space: operations
    dashboard_id: application-overview
    overwrite: true
  register: dashboard_transfer

- name: Create an independent dashboard copy with remapped identifiers
  zupersero.kibana.dashboard_transfer:
    space: template-space
    target_space: customer-a
    dashboard_id: service-health
    create_new_copies: true

- name: Preview and inspect a non-sensitive dashboard artifact
  zupersero.kibana.dashboard_transfer:
    space: staging
    target_space: production
    dashboard_id: release-readiness
    return_artifact: true
  check_mode: true
"""

RETURN = r"""
source_space:
  description: Space from which the dashboard was exported.
  returned: always
  type: str
target_space:
  description: Space into which the dashboard was or would be imported.
  returned: always
  type: str
source_dashboard:
  description: Sanitized dashboard record from the export.
  returned: always
  type: dict
source_dependencies:
  description: Sanitized dependency records included with the dashboard.
  returned: always
  type: list
  elements: dict
dependency_count:
  description: Number of dependency records in the exported artifact.
  returned: always
  type: int
dashboard:
  description: Dashboard import result, including C(destinationId) when Kibana remapped it.
  returned: when import is performed successfully
  type: dict
dashboard_id:
  description: Destination dashboard identifier, or C(null) when it cannot be predicted in check mode.
  returned: always
  type: str
imported_dependencies:
  description: Import results for the dashboard dependencies.
  returned: always
  type: list
  elements: dict
export_details:
  description: Sanitized export counts and missing-reference details.
  returned: always
  type: dict
artifact:
  description: Exact opaque NDJSON exported from the source space.
  returned: when I(return_artifact=true)
  type: str
artifact_sha256:
  description: SHA-256 digest of the exact NDJSON passed to the import API.
  returned: always
  type: str
export_status:
  description: HTTP status code returned by the export API.
  returned: always
  type: int
import_status:
  description: HTTP status code returned by the import API, or C(null) in check mode.
  returned: always
  type: int
success_count:
  description: Number of records Kibana imported successfully.
  returned: always
  type: int
errors:
  description: Per-object import errors.
  returned: always
  type: list
  elements: dict
"""

import hashlib  # noqa: E402
from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.saved_object import (  # noqa: E402
    SavedObjectService,
)


SUCCESS_CODES = (200,)
TRANSFER_MUTUALLY_EXCLUSIVE = [
    ["create_new_copies", "overwrite"],
    ["create_new_copies", "compatibility_mode"],
]


def dashboard_transfer_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete dashboard transfer argument specification."""
    argument_spec = kibana.kibana_argument_spec(include_state=False)
    argument_spec.update(
        dashboard_id=dict(type="str", required=True),
        target_space=dict(type="str", required=True),
        include_references_deep=dict(type="bool", default=True),
        fail_on_missing_references=dict(type="bool", default=True),
        overwrite=dict(type="bool", default=False),
        create_new_copies=dict(type="bool", default=False),
        compatibility_mode=dict(type="bool", default=False),
        return_artifact=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _sanitize(module: AnsibleModule, value: Any) -> Any:
    return kibana.sanitize(
        value,
        sensitive_fields=module.params["sensitive_fields"],
    )


def _validate_options(module: AnsibleModule) -> None:
    source_space = module.params["space"]
    target_space = module.params["target_space"]
    if not source_space:
        module.fail_json(msg="`space` must be a non-empty source space identifier")
    if not target_space:
        module.fail_json(msg="`target_space` must be a non-empty space identifier")
    if source_space == target_space:
        module.fail_json(msg="`space` and `target_space` must identify different spaces")
    if module.params["create_new_copies"] and module.params["overwrite"]:
        module.fail_json(
            msg="`create_new_copies` and `overwrite` are mutually exclusive"
        )
    if (
        module.params["create_new_copies"]
        and module.params["compatibility_mode"]
    ):
        module.fail_json(
            msg="`create_new_copies` and `compatibility_mode` are mutually exclusive"
        )


def _fail_export(
    module: AnsibleModule,
    message: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=message,
        changed=False,
        export_status=status,
        response=_sanitize(module, response),
    )


def _parse_export(
    module: AnsibleModule,
    status: int,
    response: Any,
) -> tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if status not in SUCCESS_CODES:
        _fail_export(
            module,
            (
                f"Kibana dashboard export failed with HTTP {status} for "
                f"dashboard {module.params['dashboard_id']!r} in source "
                f"space {module.params['space']!r}"
            ),
            status,
            response,
        )
    if not isinstance(response, str):
        _fail_export(
            module,
            "Kibana dashboard export returned a malformed non-NDJSON response",
            status,
            response,
        )
    try:
        records = SavedObjectService.parse_ndjson(response)
    except ValueError as error:
        _fail_export(
            module,
            f"Kibana dashboard export returned malformed NDJSON: {error}",
            status,
            {"content_length": len(response)},
        )

    if not records or "exportedCount" not in records[-1]:
        _fail_export(
            module,
            "Kibana dashboard export omitted its export-details record",
            status,
            {"record_count": len(records)},
        )
    export_details = records[-1]
    if (
        not isinstance(export_details.get("exportedCount"), int)
        or not isinstance(export_details.get("missingRefCount"), int)
        or not isinstance(export_details.get("missingReferences"), list)
    ):
        _fail_export(
            module,
            "Kibana dashboard export returned malformed export details",
            status,
            export_details,
        )
    objects = records[:-1]
    dashboard_id = module.params["dashboard_id"]
    dashboards = [
        record
        for record in objects
        if record.get("type") == "dashboard" and record.get("id") == dashboard_id
    ]
    if not dashboards:
        _fail_export(
            module,
            (
                f"Dashboard {dashboard_id!r} was not found in source space "
                f"{module.params['space']!r}"
            ),
            status,
            export_details,
        )
    if len(dashboards) != 1:
        _fail_export(
            module,
            "Kibana dashboard export returned the requested dashboard more than once",
            status,
            {"dashboard_count": len(dashboards)},
        )
    if (
        module.params["fail_on_missing_references"]
        and export_details["missingRefCount"] > 0
    ):
        _fail_export(
            module,
            (
                "Kibana dashboard export reported "
                f"{export_details['missingRefCount']} missing reference(s)"
            ),
            status,
            export_details,
        )
    dashboard = dashboards[0]
    dependencies = [record for record in objects if record is not dashboard]
    return response, dashboard, dependencies, export_details


def _validated_import_response(
    module: AnsibleModule,
    status: int,
    response: Any,
) -> dict[str, Any]:
    if (
        not isinstance(response, Mapping)
        or not isinstance(response.get("success"), bool)
        or not isinstance(response.get("successCount"), int)
        or (
            "errors" in response
            and (
                not isinstance(response.get("errors"), list)
                or any(
                    not isinstance(item, Mapping)
                    for item in response.get("errors", [])
                )
            )
        )
        or (
            "successResults" in response
            and (
                not isinstance(response.get("successResults"), list)
                or any(
                    not isinstance(item, Mapping)
                    for item in response.get("successResults", [])
                )
            )
        )
    ):
        module.fail_json(
            msg="Kibana dashboard import returned a malformed response",
            changed=True,
            import_status=status,
            response=_sanitize(module, response),
        )
    return dict(response)


def _base_result(
    module: AnsibleModule,
    artifact: str,
    dashboard: dict[str, Any],
    dependencies: list[dict[str, Any]],
    export_details: dict[str, Any],
    export_status: int,
) -> dict[str, Any]:
    result = {
        "source_space": module.params["space"],
        "target_space": module.params["target_space"],
        "source_dashboard": _sanitize(module, dashboard),
        "source_dependencies": _sanitize(module, dependencies),
        "dependency_count": len(dependencies),
        "dashboard": None,
        "dashboard_id": None,
        "imported_dependencies": [],
        "export_details": _sanitize(module, export_details),
        "artifact_sha256": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        "export_status": export_status,
        "import_status": None,
        "success_count": 0,
        "errors": [],
    }
    if module.params["return_artifact"]:
        result["artifact"] = artifact
    return result


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Export and import one dashboard artifact between Kibana spaces."""
    _validate_options(module)
    client = client or kibana.KibanaClient(module)
    export_status, export_response = client.saved_objects.export(
        {
            "objects": [
                {
                    "type": "dashboard",
                    "id": module.params["dashboard_id"],
                }
            ],
            "includeReferencesDeep": module.params["include_references_deep"],
            "excludeExportDetails": False,
        },
        sensitive_fields=module.params["sensitive_fields"],
        space_id=module.params["space"],
    )
    artifact, source_dashboard, source_dependencies, export_details = _parse_export(
        module,
        export_status,
        export_response,
    )
    result = _base_result(
        module,
        artifact,
        source_dashboard,
        source_dependencies,
        export_details,
        export_status,
    )
    if module.check_mode:
        module.exit_json(changed=True, **result)

    import_status, import_response = client.saved_objects.import_objects(
        artifact,
        overwrite=module.params["overwrite"],
        create_new_copies=module.params["create_new_copies"],
        compatibility_mode=module.params["compatibility_mode"],
        sensitive_fields=module.params["sensitive_fields"],
        space_id=module.params["target_space"],
    )
    if import_status not in SUCCESS_CODES:
        module.fail_json(
            msg=f"Kibana dashboard import failed with HTTP {import_status}",
            changed=False,
            import_status=import_status,
            export_status=export_status,
            response=_sanitize(module, import_response),
        )

    validated = _validated_import_response(module, import_status, import_response)
    sanitized = _sanitize(module, validated)
    success_results = sanitized.get("successResults", [])
    errors = sanitized.get("errors", [])
    result.update(
        import_status=import_status,
        success_count=validated["successCount"],
        errors=errors,
    )
    if not validated["success"]:
        module.fail_json(
            msg=(
                "Kibana dashboard import completed with "
                f"{len(errors)} object error(s)"
            ),
            changed=validated["successCount"] > 0,
            response=sanitized,
            **result,
        )

    dashboard_results = [
        item
        for item in success_results
        if item.get("type") == "dashboard"
        and item.get("id") == module.params["dashboard_id"]
    ]
    if len(dashboard_results) != 1:
        module.fail_json(
            msg=(
                "Kibana dashboard import response did not identify exactly one "
                "destination dashboard"
            ),
            changed=True,
            response=sanitized,
            **result,
        )
    imported_dashboard = dashboard_results[0]
    result.update(
        dashboard=imported_dashboard,
        dashboard_id=imported_dashboard.get("destinationId")
        or imported_dashboard["id"],
        imported_dependencies=[
            item for item in success_results if item is not imported_dashboard
        ],
    )
    module.exit_json(changed=True, **result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=dashboard_transfer_argument_spec(),
        supports_check_mode=True,
        mutually_exclusive=[
            *kibana.kibana_mutually_exclusive(),
            *TRANSFER_MUTUALLY_EXCLUSIVE,
        ],
        required_together=kibana.kibana_required_together(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
