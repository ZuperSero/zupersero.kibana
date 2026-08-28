# Kibana role

Installs Kibana from Elastic's package repository, writes `kibana.yml`, and manages
the systemd service. See the collection README for a minimal example.

## Role variables

| Variable | Default | Description |
|----------|---------|-------------|
| `kibana_version` | `9.2.1` | Kibana version to install |
| `kibana_allow_downgrade` | `false` | Allow the package manager to downgrade Kibana |
| `kibana_download_timeout` | `30` | Repository signing key download timeout in seconds |
| `kibana_package_install_timeout` | `1800` | Maximum package manager operation runtime in seconds |
| `kibana_config_path` | `/etc/kibana` | Kibana configuration directory |
| `kibana_config_content` | See defaults | Complete Kibana configuration mapping |
| `kibana_systemd_service_overrides` | `""` | Systemd drop-in content |

## Example

```yaml
- name: Install Kibana
  hosts: kibana
  become: true
  roles:
    - role: zupersero.kibana.kibana
      kibana_version: "9.2.1"
      kibana_config_content:
        server.host: "0.0.0.0"
        elasticsearch.hosts:
          - "http://elasticsearch.example.com:9200"
```
