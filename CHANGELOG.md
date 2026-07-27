# Changelog

All notable changes to `zupersero.kibana` are documented in this file.

## Unreleased

- Add shared Phase 0 API client foundations and generic object, request, and
  information modules.
- Add the typed `saved_object` module with space-aware, idempotent CRUD,
  check-mode, diff-mode, sensitive-field handling, and preservation of omitted
  attributes and references during partial updates.
- Add supported `saved_objects_export` and `saved_objects_import` modules for
  read-only opaque NDJSON exports and explicit multipart import actions.
- Add the `dashboard_transfer` workflow for check-safe, dependency-aware,
  opaque artifact transfers between Kibana spaces with predictable ID remapping
  and conflict results.
- Add typed `alerting_rule` management with explicit identifiers, preservation-
  aware updates, rule enable/disable operations, action and parameter handling,
  and check/diff support.
- Add typed `maintenance_window` management with exact-name lookup, recurring
  schedules, alert KQL scope, archive and delete lifecycles, server-derived
  status returns, and check/diff support.
