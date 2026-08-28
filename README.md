# zupersero.kibana
[![Molecule Tests](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/molecule.yml/badge.svg?branch=main)](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/molecule.yml)
[![Integration Tests](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-integration.yml/badge.svg?branch=main)](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-integration.yml)
[![Sanity Tests](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-sanity.yml/badge.svg?branch=main)](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-sanity.yml)
[![Unit Tests](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-unit.yml/badge.svg?branch=main)](https://github.com/ZuperSero/zupersero.kibana/actions/workflows/ansible-test-unit.yml)

An Ansible collection for installing, configuring, and managing Kibana. You can find idempotent modules to preform most common CRUD operations against kibana objects such as data views, alerting rules, spaces and much more. This collection in aiming to have the same amount of supported features as the official elastic terraform collection. 

## Contribution 
I implement these modules for my own use but if you are missing a module feel free to make a feature request or a PR containing the module you want included. This is something I do in my spare time so please 

## Requirements
The collection requires no other dependencies than ansible so it should work in most cases. It is tested against ansible 2.15 and higher versions. 

Also check out my other collections:
[zupersero.elastic](https://github.com/ZuperSero/zupersero.elastic) for
Elasticsearch management and
[zupersero.tailscale](https://github.com/ZuperSero/zupersero.tailscale) for
Tailscale automation.

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

## API reference

The [Ansible Galaxy collection page](https://galaxy.ansible.com/ui/repo/published/zupersero/kibana/)
and generated documentation contain the complete Kibana and Fleet module and
role reference. Start with the examples above, or use
`zupersero.kibana.kibana_object` when a typed module is not available for an
API resource.

## Examples

See the [examples directory](examples/) for ready-to-adapt playbooks. The
collection also includes detailed examples on each module's documentation page.

## Releases

See the latest published versions on [Ansible Galaxy](https://galaxy.ansible.com/ui/repo/published/zupersero/kibana/)
or browse the [GitHub releases](https://github.com/ZuperSero/zupersero.kibana/releases).

## Development

To get a local environment ready, install [uv](https://docs.astral.sh/uv/)
first, then run `just init`. It creates the collection's Python virtual
environment, installs the Ansible and Molecule tooling, and prepares the role
scenario.

```sh
just init
```

## Usage examples

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
## AI-assisted development
This project was heavily written and tested using AI tools.
