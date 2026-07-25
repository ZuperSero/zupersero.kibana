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
ansible-test integration connector
ansible-test integration data_view
ansible-test integration space
```

Targets live under `tests/integration/targets/<module_name>/`, with assertions
in `tasks/main.yml` and module routing in `aliases`. The suite covers create,
update, delete, idempotence, and check-mode behavior where supported.
