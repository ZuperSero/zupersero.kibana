# Integration Tests

These targets exercise the Kibana API modules in `zupersero.kibana`.

## Prerequisites

- Kibana available at `http://localhost:5601`
- Its Elasticsearch backend available at `http://localhost:9200`
- Username `elastic` and password `changeme`

## Running tests

```sh
# Entire integration suite
ansible-test integration

# Individual targets
ansible-test integration alerting_rule
ansible-test integration connector
ansible-test integration data_view
ansible-test integration dashboard_transfer
ansible-test integration maintenance_window
ansible-test integration agent_policy
ansible-test integration fleet_package
ansible-test integration fleet_output
ansible-test integration fleet_proxy
ansible-test integration fleet_server_host
ansible-test integration agent_download_source
ansible-test integration enrollment_token
ansible-test integration package_policy
ansible-test integration role
ansible-test integration saved_object
ansible-test integration saved_objects_export
ansible-test integration saved_objects_import
ansible-test integration space
```

Targets live under `tests/integration/targets/<module_name>/`, with assertions
in `tasks/main.yml` and module routing in `aliases`. The suite covers create,
update, delete, idempotence, and check-mode behavior where supported.

The `package_policy` target additionally requires the Fleet `system` package to
be installed. It fails with an explicit prerequisite message when the package
registry is unavailable or the package has not been installed; it does not
silently skip Fleet coverage. Fleet privileges sufficient to create and delete
agent and package policies are required.

The Fleet administration targets require Fleet settings privileges and a trial
or higher Kibana license. The enrollment-token target also requires an existing
agent policy and always redacts the generated enrollment API key.
