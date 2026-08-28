# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export Kibana saved objects as opaque NDJSON."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: saved_objects_export
short_description: Export Kibana saved objects
description:
  - Exports selected Kibana saved objects with the supported saved objects export API.
  - This is a read-only operation and always reports I(changed=false), including in check mode.
  - Returns both the opaque NDJSON export and a parsed, sanitized object list for inspection.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  types:
    description:
      - Saved object types to export.
      - Use C(*) to export every available type.
      - Mutually exclusive with I(objects).
    type: list
    elements: str
  objects:
    description:
      - Specific saved objects to export.
      - Mutually exclusive with I(types).
    type: list
    elements: dict
    suboptions:
      type:
        description: Saved object type.
        type: str
        required: true
      id:
        description: Saved object identifier.
        type: str
        required: true
  include_references_deep:
    description: Whether to include the complete reference graph.
    type: bool
    default: false
  exclude_export_details:
    description: Whether to omit Kibana's export-details record from the NDJSON.
    type: bool
    default: false
  search:
    description: Simple query string used to filter objects selected by I(types).
    type: str
  has_reference:
    description: Export objects that refer to any of these saved objects.
    type: list
    elements: dict
    suboptions:
      type:
        description: Referenced saved object type.
        type: str
        required: true
      id:
        description: Referenced saved object identifier.
        type: str
        required: true
  sensitive_fields:
    description:
      - Dot-separated fields redacted from I(objects), I(export_details), and API failures.
      - This does not alter I(ndjson), which Kibana requires callers to preserve as opaque data.
    type: list
    elements: str
    default: []
notes:
  - I(types) or I(objects) is required.
  - The I(space) option selects the space from which objects are exported.
  - Exported NDJSON is not backward compatible with older Kibana versions.
  - I(ndjson) can contain sensitive saved-object data. Protect task output with Ansible's C(no_log) when appropriate.
"""

EXAMPLES = r"""
- name: Export one dashboard and all of its dependencies
  zupersero.kibana.saved_objects_export:
    objects:
      - type: dashboard
        id: application-overview
    include_references_deep: true
    exclude_export_details: true
  register: dashboard_export

- name: Export every data view in a space
  zupersero.kibana.saved_objects_export:
    space: operations
    types:
      - index-pattern

- name: Use environment-based authentication
  zupersero.kibana.saved_objects_export:
    types:
      - dashboard
  environment:
    KIBANA_URL: https://kibana.example.com
    KIBANA_API_KEY: your-encoded-api-key
"""

RETURN = r"""
ndjson:
  description:
    - Exact opaque NDJSON returned by Kibana.
    - Preserve this value unchanged when passing it to M(zupersero.kibana.saved_objects_import).
  returned: always
  type: str
objects:
  description: Exported saved-object records, excluding the export-details record.
  returned: always
  type: list
  elements: dict
export_details:
  description: Kibana export counts and missing-reference details, or C(null) when omitted.
  returned: always
  type: dict
object_count:
  description: Number of saved-object records in I(objects).
  returned: always
  type: int
status:
  description: HTTP status code returned by Kibana.
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


EXPORT_SUCCESS_CODES = (200,)


def saved_objects_export_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete saved-object export argument specification."""
    argument_spec = kibana.kibana_argument_spec(include_state=False)
    reference_spec = dict(
        type="list",
        elements="dict",
        options=dict(
            type=dict(type="str", required=True),
            id=dict(type="str", required=True),
        ),
    )
    argument_spec.update(
        types=dict(type="list", elements="str"),
        objects=reference_spec,
        include_references_deep=dict(type="bool", default=False),
        exclude_export_details=dict(type="bool", default=False),
        search=dict(type="str"),
        has_reference=reference_spec,
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def build_export_payload(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate Ansible option names to the supported Kibana request shape."""
    payload = {
        "includeReferencesDeep": params["include_references_deep"],
        "excludeExportDetails": params["exclude_export_details"],
    }
    if params.get("types") is not None:
        payload["type"] = params["types"]
    if params.get("objects") is not None:
        payload["objects"] = params["objects"]
    if params.get("search") is not None:
        payload["search"] = params["search"]
    if params.get("has_reference") is not None:
        payload["hasReference"] = params["has_reference"]
    return payload


def _fail_export(
    module: AnsibleModule,
    message: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=message,
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params["sensitive_fields"],
        ),
    )


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Run a read-only saved-object export."""
    client = client or kibana.KibanaClient(module)
    status, response = client.saved_objects.export(
        build_export_payload(module.params),
        sensitive_fields=module.params["sensitive_fields"],
    )
    if status not in EXPORT_SUCCESS_CODES:
        _fail_export(
            module,
            f"Kibana saved objects export failed with HTTP {status}",
            status,
            response,
        )
    if not isinstance(response, str):
        _fail_export(
            module,
            "Kibana saved objects export returned a malformed non-NDJSON response",
            status,
            response,
        )
    try:
        records = SavedObjectService.parse_ndjson(response)
    except ValueError as error:
        _fail_export(
            module,
            f"Kibana saved objects export returned malformed NDJSON: {error}",
            status,
            {"content_length": len(response)},
        )

    export_details = None
    if records and "exportedCount" in records[-1]:
        export_details = records.pop()
    sensitive_fields = module.params["sensitive_fields"]
    module.exit_json(
        changed=False,
        ndjson=response,
        objects=kibana.sanitize(records, sensitive_fields=sensitive_fields),
        export_details=kibana.sanitize(
            export_details,
            sensitive_fields=sensitive_fields,
        ),
        object_count=len(records),
        status=status,
    )


def main() -> None:
    module = AnsibleModule(
        argument_spec=saved_objects_export_argument_spec(),
        supports_check_mode=True,
        required_one_of=[["types", "objects"]],
        mutually_exclusive=[
            *kibana.kibana_mutually_exclusive(),
            ["types", "objects"],
        ],
        required_together=kibana.kibana_required_together(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
