# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Space-aware services for Kibana alerting resources."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from ..kibana import KibanaClient


class AlertingRuleService:
    """Perform CRUD and enabled-state operations for Kibana alerting rules."""

    def __init__(self, client: KibanaClient) -> None:
        self.client = client

    def _path(self, rule_id: str) -> str:
        path = f"/api/alerting/rule/{quote(rule_id, safe='')}"
        return self.client.space_path(path)

    def get(
        self,
        rule_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Retrieve one alerting rule."""
        return self.client.request(
            "GET",
            self._path(rule_id),
            sensitive_fields=sensitive_fields,
        )

    def create(
        self,
        rule_id: str,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Create an alerting rule with an explicit identifier."""
        return self.client.request(
            "POST",
            self._path(rule_id),
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def update(
        self,
        rule_id: str,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Update the writable definition of an alerting rule."""
        return self.client.request(
            "PUT",
            self._path(rule_id),
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def set_enabled(
        self,
        rule_id: str,
        enabled: bool,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Enable or disable an alerting rule."""
        operation = "_enable" if enabled else "_disable"
        data = None if enabled else {}
        return self.client.request(
            "POST",
            f"{self._path(rule_id)}/{operation}",
            data=data,
            sensitive_fields=sensitive_fields,
        )

    def delete(
        self,
        rule_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Delete an alerting rule."""
        return self.client.request(
            "DELETE",
            self._path(rule_id),
            sensitive_fields=sensitive_fields,
        )

    def rule_types(
        self,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Return rule types authorized in the selected space."""
        return self.client.request(
            "GET",
            self.client.space_path("/api/alerting/rule_types"),
            sensitive_fields=sensitive_fields,
        )


class MaintenanceWindowService:
    """Perform CRUD, lookup, and archive operations for maintenance windows."""

    def __init__(self, client: KibanaClient) -> None:
        self.client = client
        self.base_path = self.client.space_path("/api/maintenance_window")

    def _path(self, window_id: str) -> str:
        return f"{self.base_path}/{quote(window_id, safe='')}"

    def get(
        self,
        window_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Retrieve one maintenance window."""
        return self.client.request(
            "GET",
            self._path(window_id),
            sensitive_fields=sensitive_fields,
        )

    def find(
        self,
        title: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Find maintenance windows by title."""
        return self.client.request(
            "GET",
            f"{self.base_path}/_find",
            query={"title": title, "page": 1, "per_page": 100},
            sensitive_fields=sensitive_fields,
        )

    def create(
        self,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Create a maintenance window."""
        return self.client.request(
            "POST",
            self.base_path,
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def update(
        self,
        window_id: str,
        payload: dict[str, Any],
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Partially update a maintenance window."""
        return self.client.request(
            "PATCH",
            self._path(window_id),
            data=payload,
            sensitive_fields=sensitive_fields,
        )

    def archive(
        self,
        window_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Archive a maintenance window."""
        return self.client.request(
            "POST",
            f"{self._path(window_id)}/_archive",
            sensitive_fields=sensitive_fields,
        )

    def delete(
        self,
        window_id: str,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, Any]:
        """Delete a maintenance window."""
        return self.client.request(
            "DELETE",
            self._path(window_id),
            sensitive_fields=sensitive_fields,
        )
