:orphan:

Index of all Collection Environment Variables
=============================================

The Kibana and Fleet API modules read these controller-side environment
variables when the corresponding module argument is omitted. Explicit module
arguments take precedence. Keep credentials, tokens, headers, and private key
material in your secret manager rather than committing them to playbooks.

Connection and authentication
-----------------------------

``KIBANA_URL``
  Single Kibana base URL (default: ``http://localhost:5601``).
``KIBANA_URLS``
  Comma-separated URLs used for endpoint failover; mutually exclusive with
  ``KIBANA_URL``.
``KIBANA_USERNAME`` / ``KIBANA_PASSWORD``
  Basic-auth credentials, used together.
``KIBANA_API_KEY``
  Encoded Kibana API key.
``KIBANA_BEARER_TOKEN``
  Bearer token for HTTP authentication.
``KIBANA_HEADERS``
  JSON object of additional HTTP headers.
``KIBANA_SPACE``
  Default Kibana space for space-aware APIs (default: ``default``).

TLS and client certificates
---------------------------

``KIBANA_VALIDATE_CERTS``
  Enable or disable TLS certificate validation (default: ``true``).
``KIBANA_CA_PATH`` / ``KIBANA_CA_DATA``
  PEM CA bundle path or inline PEM data; use only one.
``KIBANA_CLIENT_CERT`` / ``KIBANA_CLIENT_KEY``
  PEM client certificate and private-key paths.
``KIBANA_CERTIFICATE_FINGERPRINT``
  SHA-256 fingerprint for HTTPS certificate pinning.

Transport and retries
---------------------

``KIBANA_TIMEOUT``
  Request timeout in seconds (default: ``30``).
``KIBANA_RETRIES``
  Retry attempts after the initial request (default: ``3``).
``KIBANA_RETRY_PAUSE``
  Initial retry delay in seconds (default: ``1.0``).
``KIBANA_RETRY_MUTATING_REQUESTS``
  Allow retries for mutating requests (default: ``false``).

``retry_status_codes`` has no environment-variable fallback. The compatibility
arguments ``url_username``, ``url_password``, and ``force_basic_auth`` are also
module arguments only.
