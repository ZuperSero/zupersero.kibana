# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Service for Kibana saved-object CRUD operations."""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from ..kibana import KibanaClient


class SavedObjectService:
    """Perform space-aware requests to the Kibana saved objects API."""

    def __init__(self, client: KibanaClient) -> None:
        self.client = client

    def _path(self, object_type: str, object_id: str) -> str:
        path = (
            f"/api/saved_objects/{quote(object_type, safe='')}/"
            f"{quote(object_id, safe='')}"
        )
        return self.client.space_path(path)

    def _space_path(self, path: str, space_id: str | None) -> str:
        if space_id is None:
            return self.client.space_path(path)
        return self.client.space_path(path, space_id=space_id)

    def get(
        self,
        object_type: str,
        object_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Retrieve a saved object by type and ID."""
        return self.client.request(
            "GET",
            self._path(object_type, object_id),
            sensitive_fields=sensitive_fields,
        )

    def create(
        self,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Create a saved object with an explicit ID."""
        return self.client.request(
            "POST",
            self._path(object_type, object_id),
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def update(
        self,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Update a saved object's managed attributes and references."""
        return self.client.request(
            "PUT",
            self._path(object_type, object_id),
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def delete(
        self,
        object_type: str,
        object_id: str,
        force: bool = False,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Delete a saved object, optionally across all namespaces."""
        query = {"force": "true"} if force else None
        return self.client.request(
            "DELETE",
            self._path(object_type, object_id),
            query=query,
            sensitive_fields=sensitive_fields,
        )

    @staticmethod
    def parse_ndjson(content: str) -> list[dict[str, Any]]:
        """Validate NDJSON and return its object records without changing the input."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("saved object NDJSON content must not be empty")
        records = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"saved object NDJSON line {line_number} is not valid JSON: {error}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"saved object NDJSON line {line_number} must contain an object"
                )
            records.append(record)
        if not records:
            raise ValueError("saved object NDJSON content must contain an object")
        return records

    @staticmethod
    def _multipart_body(
        content: str,
        boundary: str | None = None,
    ) -> tuple[bytes, str]:
        """Wrap opaque NDJSON in the multipart form required by Kibana."""
        encoded = content.encode("utf-8")
        boundary = boundary or f"ansible-{secrets.token_hex(24)}"
        if any(character in boundary for character in '\r\n"'):
            raise ValueError("multipart boundary contains unsafe characters")
        boundary_bytes = boundary.encode("ascii")
        if boundary_bytes in encoded:
            raise ValueError("multipart boundary unexpectedly occurs in NDJSON content")
        body = b"".join(
            (
                b"--",
                boundary_bytes,
                b"\r\n",
                b'Content-Disposition: form-data; name="file"; '
                b'filename="saved_objects.ndjson"\r\n',
                b"Content-Type: application/x-ndjson\r\n\r\n",
                encoded,
                b"\r\n--",
                boundary_bytes,
                b"--\r\n",
            )
        )
        return body, f"multipart/form-data; boundary={boundary}"

    def export(
        self,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
        space_id: str | None = None,
    ) -> tuple[int, Any]:
        """Export a set of saved objects as opaque NDJSON."""
        return self.client.request(
            "POST",
            self._space_path("/api/saved_objects/_export", space_id),
            data=payload,
            sensitive_fields=sensitive_fields,
            deserialize_json=False,
            sanitize_success_response=False,
        )

    def import_objects(
        self,
        content: str,
        overwrite: bool = False,
        create_new_copies: bool = False,
        compatibility_mode: bool = False,
        sensitive_fields: Iterable[str] | None = None,
        space_id: str | None = None,
    ) -> tuple[int, Any]:
        """Import an opaque saved-object NDJSON export."""
        self.parse_ndjson(content)
        body, content_type = self._multipart_body(content)
        query = {
            key: "true"
            for key, enabled in (
                ("overwrite", overwrite),
                ("createNewCopies", create_new_copies),
                ("compatibilityMode", compatibility_mode),
            )
            if enabled
        }
        return self.client.request(
            "POST",
            self._space_path("/api/saved_objects/_import", space_id),
            data=body,
            headers={"Content-Type": content_type},
            query=query or None,
            sensitive_fields=sensitive_fields,
            serialize_json=False,
        )
