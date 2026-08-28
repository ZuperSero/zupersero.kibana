# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manage a Kibana Fleet output."""

DOCUMENTATION = r"""
---
module: fleet_output
short_description: Manage a Kibana Fleet output
description: Manage Elasticsearch, remote Elasticsearch, Logstash, or Kafka Fleet outputs.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id: {description: Server-generated output identifier., type: str}
  name: {description: Output name., type: str}
  type: {description: Output type., type: str, choices: [elasticsearch, remote_elasticsearch, logstash, kafka]}
  hosts: {description: Output hosts., type: list, elements: str}
  proxy_id: {description: Fleet proxy identifier., type: str}
  preset: {description: Output preset., type: str, choices: [balanced, custom, throughput, scale, latency]}
  config_yaml: {description: Additional output configuration YAML., type: str}
  allow_edit: {description: Spaces allowed to edit the output., type: list, elements: str}
  ssl: {description: TLS output settings., type: dict}
  shipper: {description: Shipper queue settings., type: dict}
  settings: {description: Additional type-specific output settings., type: dict}
  output_username: {description: Kafka output username., type: str}
  output_password: {description: Kafka output password., type: str}
  service_token: {description: Remote Elasticsearch service token., type: str}
  kibana_api_key: {description: Remote Elasticsearch Kibana API key., type: str}
  kibana_url: {description: Remote Elasticsearch Kibana URL., type: str}
  sensitive_fields: {description: Response paths to redact., type: list, elements: str, default: []}
  replace: {description: Reserved for future authoritative replacement support., type: bool, default: false}
  state: {description: Desired output state., type: str, choices: [present, absent], default: present}
notes:
  - Output credentials and TLS material are never returned unsanitized.
"""
EXAMPLES = r"""
- name: Configure the default Elasticsearch output
  zupersero.kibana.fleet_output:
    name: Primary Elasticsearch
    type: elasticsearch
    hosts: [https://elasticsearch.example.test:9200]
    ssl: {verification_mode: full}
"""
RETURN = r"""
fleet_output:
  description: Current or resulting output with sensitive values redacted.
  returned: always
  type: dict
status:
  description: HTTP status of the last operation.
  returned: always
  type: int
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource  # noqa: E402


CONFIG = {
    "service": "fleet_outputs", "resource": "output", "result": "fleet_output",
    "required": ("name", "type", "hosts"),
    "fields": (
        "name", "type", "hosts", "proxy_id", "preset", "config_yaml",
        "allow_edit", "ssl", "shipper", "settings", "output_username",
        "output_password", "service_token", "kibana_api_key", "kibana_url",
    ),
    "spec": {
        "type": dict(type="str", choices=["elasticsearch", "remote_elasticsearch", "logstash", "kafka"]),
        "hosts": dict(type="list", elements="str"),
        "proxy_id": dict(type="str"), "preset": dict(type="str", choices=["balanced", "custom", "throughput", "scale", "latency"]),
        "config_yaml": dict(type="str"), "allow_edit": dict(type="list", elements="str"),
        "ssl": dict(type="dict", no_log=True), "shipper": dict(type="dict"),
        "settings": dict(type="dict", no_log=True),
        "output_username": dict(type="str", no_log=True), "output_password": dict(type="str", no_log=True),
        "service_token": dict(type="str", no_log=True), "kibana_api_key": dict(type="str", no_log=True),
        "kibana_url": dict(type="str"),
    },
}


def fleet_output_argument_spec():
    return fleet_resource.argument_spec(CONFIG)


def main():
    module = AnsibleModule(
        argument_spec=fleet_output_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    fleet_resource.run_module(module, kibana.KibanaClient(module), CONFIG)


if __name__ == "__main__":
    main()
