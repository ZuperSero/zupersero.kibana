# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Import opaque Kibana saved-object NDJSON."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: saved_objects_import
short_description: Import Kibana saved objects
description:
  - Imports opaque NDJSON produced by the supported saved objects export API.
  - This is an explicit action module, not an idempotent CRUD module.
  - A successfully accepted import reports I(changed=true), even when overwriting equivalent objects.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  content:
    description:
      - Opaque saved-object NDJSON produced by Kibana.
      - The value is treated as sensitive and is uploaded without rewriting its records.
    type: str
    required: true
  overwrite:
    description:
      - Overwrite saved objects when they already exist.
      - Mutually exclusive with I(create_new_copies).
    type: bool
    default: false
  create_new_copies:
    description:
      - Regenerate object identifiers and reset each object's origin.
      - Mutually exclusive with I(overwrite) and I(compatibility_mode).
    type: bool
    default: false
  compatibility_mode:
    description:
      - Apply Kibana compatibility adjustments during import.
      - Use only when an export has cross-version compatibility problems.
      - Mutually exclusive with I(create_new_copies).
    type: bool
    default: false
  sensitive_fields:
    description: Dot-separated response fields redacted from output and API failures.
    type: list
    elements: str
    default: []
notes:
  - The I(space) option selects the space into which objects are imported.
  - In check mode, NDJSON and option compatibility are validated locally, no API request is sent, and the module predicts I(changed=true).
  - Saved objects can be imported only into the same Kibana version, a newer minor of the same major, or the next major.
"""

EXAMPLES = r"""
- name: Export one dashboard
  zupersero.kibana.saved_objects_export:
    objects:
      - type: dashboard
        id: application-overview
    include_references_deep: true
    exclude_export_details: true
  register: dashboard_export

- name: Import the dashboard into another space
  zupersero.kibana.saved_objects_import:
    space: operations
    content: "{{ dashboard_export.ndjson }}"
    overwrite: true

- name: Import controller-side NDJSON with an explicit lookup
  zupersero.kibana.saved_objects_import:
    content: "{{ lookup('ansible.builtin.file', 'saved_objects.ndjson') }}"
    create_new_copies: true
"""

RETURN = r"""
response:
  description: Sanitized import response returned by Kibana.
  returned: when the request is performed
  type: dict
success_count:
  description: Number of records Kibana imported successfully.
  returned: always
  type: int
errors:
  description: Per-object import errors.
  returned: always
  type: list
  elements: dict
success_results:
  description: Successfully imported objects and destination identifiers.
  returned: always
  type: list
  elements: dict
status:
  description: HTTP status code, or C(null) in check mode.
  returned: always
  type: int
record_count:
  description: Number of non-empty NDJSON records validated from I(content).
  returned: always
  type: int
"""

from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.saved_object import (  # noqa: E402
    SavedObjectService,
)


IMPORT_SUCCESS_CODES = (200,)
IMPORT_MUTUALLY_EXCLUSIVE = [
    ["create_new_copies", "overwrite"],
    ["create_new_copies", "compatibility_mode"],
]


def saved_objects_import_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete saved-object import argument specification."""
    argument_spec = kibana.kibana_argument_spec(include_state=False)
    argument_spec.update(
        content=dict(type="str", required=True, no_log=True),
        overwrite=dict(type="bool", default=False),
        create_new_copies=dict(type="bool", default=False),
        compatibility_mode=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _validate_options(module: AnsibleModule) -> None:
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


def _validated_response(
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
            and not isinstance(response.get("errors"), list)
        )
        or (
            "successResults" in response
            and not isinstance(response.get("successResults"), list)
        )
    ):
        module.fail_json(
            msg="Kibana saved objects import returned a malformed response",
            changed=True,
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )
    return dict(response)


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Validate and perform an explicit saved-object import action."""
    _validate_options(module)
    try:
        records = SavedObjectService.parse_ndjson(module.params["content"])
    except ValueError as error:
        module.fail_json(msg=f"Invalid saved object NDJSON: {error}")

    if module.check_mode:
        module.exit_json(
            changed=True,
            response=None,
            success_count=0,
            errors=[],
            success_results=[],
            status=None,
            record_count=len(records),
        )

    client = client or kibana.KibanaClient(module)
    status, response = client.saved_objects.import_objects(
        module.params["content"],
        overwrite=module.params["overwrite"],
        create_new_copies=module.params["create_new_copies"],
        compatibility_mode=module.params["compatibility_mode"],
        sensitive_fields=module.params["sensitive_fields"],
    )
    if status not in IMPORT_SUCCESS_CODES:
        module.fail_json(
            msg=f"Kibana saved objects import failed with HTTP {status}",
            changed=False,
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )

    validated = _validated_response(module, status, response)
    sanitized = kibana.sanitize(
        validated,
        sensitive_fields=module.params["sensitive_fields"],
    )
    success_count = validated["successCount"]
    errors = sanitized.get("errors", [])
    success_results = sanitized.get("successResults", [])
    if not validated["success"]:
        module.fail_json(
            msg=(
                "Kibana saved objects import completed with "
                f"{len(errors)} object error(s)"
            ),
            changed=success_count > 0,
            status=status,
            response=sanitized,
            success_count=success_count,
            errors=errors,
            success_results=success_results,
        )
    module.exit_json(
        changed=True,
        response=sanitized,
        success_count=success_count,
        errors=errors,
        success_results=success_results,
        status=status,
        record_count=len(records),
    )


def main() -> None:
    module = AnsibleModule(
        argument_spec=saved_objects_import_argument_spec(),
        supports_check_mode=True,
        mutually_exclusive=[
            *kibana.kibana_mutually_exclusive(),
            *IMPORT_MUTUALLY_EXCLUSIVE,
        ],
        required_together=kibana.kibana_required_together(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
