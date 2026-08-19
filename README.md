# zupersero.kibana

An Ansible collection for installing, configuring, and managing Kibana.

## Installation

```sh
ansible-galaxy collection install zupersero.kibana
```

API modules use `KIBANA_URL` and either `KIBANA_USERNAME` with
`KIBANA_PASSWORD`, or `KIBANA_API_KEY`. Optional settings include
`KIBANA_SPACE` and `KIBANA_VALIDATE_CERTS`.

Included API modules:

- `zupersero.kibana.alerting_rule`
- `zupersero.kibana.connector`
- `zupersero.kibana.data_view`
- `zupersero.kibana.dashboard_transfer`
- `zupersero.kibana.fleet_package`
- `zupersero.kibana.maintenance_window`
- `zupersero.kibana.agent_policy`
- `zupersero.kibana.package_policy`
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

## Example

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
