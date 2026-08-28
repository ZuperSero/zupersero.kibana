# zupersero.kibana

An Ansible collection for installing, configuring, and managing Kibana.

## Installation

```sh
ansible-galaxy collection install zupersero.kibana
```

API modules use `KIBANA_URL` and either `KIBANA_USERNAME` with
`KIBANA_PASSWORD`, or `KIBANA_API_KEY`. Optional settings include
`KIBANA_SPACE` and `KIBANA_VALIDATE_CERTS`.

All Kibana and Fleet API modules belong to the `zupersero.kibana.kibana`
module-defaults group:

```yaml
module_defaults:
  group/zupersero.kibana.kibana:
    url: https://kibana.example.com:5601
    api_key: "{{ kibana_api_key }}"
```

Included API modules:

- `zupersero.kibana.alerting_rule`
- `zupersero.kibana.connector`
- `zupersero.kibana.data_view`
- `zupersero.kibana.dashboard_transfer`
- `zupersero.kibana.fleet_package`
- `zupersero.kibana.fleet_output`
- `zupersero.kibana.fleet_proxy`
- `zupersero.kibana.fleet_server_host`
- `zupersero.kibana.agent_download_source`
- `zupersero.kibana.enrollment_token`
- `zupersero.kibana.maintenance_window`
- `zupersero.kibana.agent_policy`
- `zupersero.kibana.package_policy`
- `zupersero.kibana.role`
- `zupersero.kibana.saved_object`
- `zupersero.kibana.saved_objects_export`
- `zupersero.kibana.saved_objects_import`
- `zupersero.kibana.space`

## Development

Install the development environment and run the role scenario:

```sh
just init
just molecule
```

Run static and Ansible collection checks with:

```sh
just ruff
just sanity
just integration
```

The local Fleet integration tests can use the Elasticsearch trial license.
Run this against an authorized, disposable development cluster only:

```sh
just activate-trial
```

The recipe uses `ELASTICSEARCH_URL`, `ELASTICSEARCH_USERNAME`, and
`ELASTICSEARCH_PASSWORD` when set, defaulting to `http://localhost:9200`,
`elastic`, and `changeme`. It fails unless Elasticsearch confirms that the
trial was started; it does not expose credentials in its output.

## Example

Custom Kibana roles preserve omitted privilege sections during updates. Set
`replace: true` when the supplied role definition should clear omitted sections:

```yaml
- name: Manage a Kibana read-only role
  zupersero.kibana.role:
    name: observability-reader
    description: Read-only observability access
    elasticsearch:
      cluster: [monitor]
      indices:
        - names: ["logs-*"]
          privileges: [read, view_index_metadata]
    kibana:
      - base: [read]
        feature:
          dashboard: [read]
        spaces: [default]
```

Fleet integration policies require the referenced package to be installed in
Kibana and attach to an existing Fleet agent policy:

```yaml
- name: Configure the system integration
  zupersero.kibana.package_policy:
    name: Linux system metrics
    package: system
    package_version: 1.49.0
    policy_id: fleet-agent-policy
    inputs: {}
    vars: {}
```

```yaml
- name: Install Kibana
  hosts: kibana
  become: true
  roles:
    - role: zupersero.kibana.kibana
      vars:
        kibana_config_content:
          server.host: "0.0.0.0"
          elasticsearch.hosts:
            - "http://elasticsearch:9200"
```
