# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fleet package-policy API service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from ..kibana import KibanaClient
else:
    from ansible_collections.zupersero.kibana.plugins.module_utils.kibana import (
        KibanaClient,
    )


class PackagePolicyService:
    """CRUD operations for Fleet integration (package) policies."""

    def __init__(self, client: KibanaClient) -> None:
        self.client = client

    @staticmethod
    def _path_component(value: str) -> str:
        return quote(value, safe="")

    def get(self, policy_id: str) -> tuple[int, dict | None]:
        """Read one package policy by its server-generated identifier."""
        path = f"api/fleet/package_policies/{self._path_component(policy_id)}"
        return self.client.get(path)

    def list(self, page: int = 1, per_page: int = 100) -> tuple[int, dict | None]:
        """List package policies, allowing the module to find generated IDs."""
        return self.client.get(
            f"api/fleet/package_policies?page={page}&perPage={per_page}"
        )

    def create(self, data: dict) -> tuple[int, dict | None]:
        return self.client.post("api/fleet/package_policies", data=data)

    def update(self, policy_id: str, data: dict) -> tuple[int, dict | None]:
        path = f"api/fleet/package_policies/{self._path_component(policy_id)}"
        return self.client.put(path, data=data)

    def delete(self, policy_id: str, force: bool = False) -> tuple[int, dict | None]:
        path = f"api/fleet/package_policies/{self._path_component(policy_id)}"
        if force:
            path += "?force=true"
        return self.client.delete(path)
