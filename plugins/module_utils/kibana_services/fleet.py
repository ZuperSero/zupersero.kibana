# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fleet administration API services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from ..kibana import KibanaClient


class FleetResourceService:
    """CRUD service for Fleet resources with conventional item/list replies."""

    def __init__(self, client: KibanaClient, endpoint: str) -> None:
        self.client = client
        self.endpoint = endpoint.strip("/")

    def _path(self, identifier: str | None = None) -> str:
        path = f"api/fleet/{self.endpoint}"
        if identifier is not None:
            path += f"/{quote(identifier, safe='')}"
        return self.client.space_path(path)

    def list(self, page: int = 1, per_page: int = 100) -> tuple[int, Any]:
        return self.client.request(
            "GET", self._path(), query={"page": page, "perPage": per_page}
        )

    def get(self, identifier: str) -> tuple[int, Any]:
        return self.client.get(self._path(identifier))

    def create(self, data: dict[str, Any]) -> tuple[int, Any]:
        return self.client.post(self._path(), data=data)

    def update(self, identifier: str, data: dict[str, Any]) -> tuple[int, Any]:
        return self.client.put(self._path(identifier), data=data)

    def delete(self, identifier: str) -> tuple[int, Any]:
        return self.client.delete(self._path(identifier))


class FleetOutputService(FleetResourceService):
    """Fleet output CRUD and health operations."""

    def __init__(self, client: KibanaClient) -> None:
        super().__init__(client, "outputs")

    def health(self, identifier: str) -> tuple[int, Any]:
        return self.client.get(f"{self._path(identifier)}/health")


class FleetProxyService(FleetResourceService):
    """Fleet proxy CRUD operations."""

    def __init__(self, client: KibanaClient) -> None:
        super().__init__(client, "proxies")


class FleetServerHostService(FleetResourceService):
    """Fleet Server host CRUD operations."""

    def __init__(self, client: KibanaClient) -> None:
        super().__init__(client, "fleet_server_hosts")


class AgentDownloadSourceService(FleetResourceService):
    """Elastic Agent binary download-source CRUD operations."""

    def __init__(self, client: KibanaClient) -> None:
        super().__init__(client, "agent_download_sources")


class EnrollmentTokenService:
    """Fleet enrollment API-key creation, lookup, and revocation."""

    def __init__(self, client: KibanaClient) -> None:
        self.client = client

    def _path(self, identifier: str | None = None) -> str:
        path = "api/fleet/enrollment_api_keys"
        if identifier is not None:
            path += f"/{quote(identifier, safe='')}"
        return self.client.space_path(path)

    def list(self, page: int = 1, per_page: int = 100) -> tuple[int, Any]:
        return self.client.get(self._path())

    def get(self, identifier: str) -> tuple[int, Any]:
        return self.client.get(self._path(identifier))

    def create(self, data: dict[str, Any]) -> tuple[int, Any]:
        return self.client.post(self._path(), data=data)

    def delete(self, identifier: str) -> tuple[int, Any]:
        return self.client.delete(self._path(identifier))
