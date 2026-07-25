# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later


class ModuleDocFragment:
    DOCUMENTATION = r"""
options:
  url:
    description:
      - URL of the Kibana instance.
      - Can also be set with the C(KIBANA_URL) environment variable.
    type: str
  username:
    description:
      - Username for basic authentication.
    type: str
  password:
    description:
      - Password for basic authentication.
    type: str
  api_key:
    description:
      - Kibana API key used instead of basic authentication.
    type: str
  space:
    description:
      - Kibana space used for API requests.
    type: str
    default: default
  validate_certs:
    description:
      - Whether to validate TLS certificates.
    type: bool
    default: true
  client_cert:
    description:
      - PEM-formatted client certificate chain.
    type: path
  client_key:
    description:
      - PEM-formatted private key for the client certificate.
    type: path
  force_basic_auth:
    description:
      - Send the basic authentication header with the initial request.
    type: bool
    default: false
  url_username:
    description:
      - Username embedded in URL authentication.
    type: str
  url_password:
    description:
      - Password embedded in URL authentication.
    type: str
  timeout:
    description:
      - API request timeout in seconds.
    type: int
    default: 30
  retries:
    description:
      - Number of attempts for retryable API failures.
    type: int
    default: 3
  retry_pause:
    description:
      - Base delay between retry attempts.
    type: float
    default: 1.0
"""
