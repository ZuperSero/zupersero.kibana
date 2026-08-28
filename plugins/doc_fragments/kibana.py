# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later


class ModuleDocFragment:
    DOCUMENTATION = r"""
options:
  url:
    description:
      - URL of a Kibana endpoint.
      - Can also be set with the E(KIBANA_URL) environment variable.
      - Mutually exclusive with I(urls).
    type: str
  urls:
    description:
      - Kibana endpoints tried in order across retry attempts.
      - Can also be set with the E(KIBANA_URLS) environment variable.
      - Mutually exclusive with I(url).
    type: list
    elements: str
  username:
    description:
      - Username for basic authentication.
      - Can also be set with the E(KIBANA_USERNAME) environment variable.
    type: str
  password:
    description:
      - Password for basic authentication.
      - Can also be set with the E(KIBANA_PASSWORD) environment variable.
    type: str
  api_key:
    description:
      - Encoded API key for C(ApiKey) authentication.
      - Can also be set with the E(KIBANA_API_KEY) environment variable.
    type: str
  bearer_token:
    description:
      - Token for C(Bearer) authentication.
      - Can also be set with the E(KIBANA_BEARER_TOKEN) environment variable.
    type: str
  headers:
    description:
      - Additional HTTP headers.
      - Header values are treated as sensitive and are redacted from failures.
      - Can also be set as a JSON object with the E(KIBANA_HEADERS) environment variable.
    type: dict
    default: {}
  space:
    description:
      - Kibana space used by modules that support space-scoped APIs.
      - Can also be set with the E(KIBANA_SPACE) environment variable.
    type: str
    default: default
  validate_certs:
    description:
      - Whether to validate TLS certificates.
      - Can also be set with the E(KIBANA_VALIDATE_CERTS) environment variable.
    type: bool
    default: true
  ca_path:
    description:
      - Path to a PEM CA certificate bundle.
      - Can also be set with the E(KIBANA_CA_PATH) environment variable.
    type: path
  ca_data:
    description:
      - PEM CA certificate data.
      - Can also be set with the E(KIBANA_CA_DATA) environment variable.
    type: str
  client_cert:
    description:
      - Path to a PEM client certificate chain.
      - Can also be set with the E(KIBANA_CLIENT_CERT) environment variable.
    type: path
  client_key:
    description:
      - Path to the private key for I(client_cert).
      - Can also be set with the E(KIBANA_CLIENT_KEY) environment variable.
    type: path
  certificate_fingerprint:
    description:
      - SHA-256 fingerprint of the expected TLS peer certificate.
      - Can also be set with the E(KIBANA_CERTIFICATE_FINGERPRINT) environment variable.
      - The certificate is verified in a credential-free TLS preflight before HTTP headers are sent.
      - May only be used with HTTPS endpoints.
    type: str
  timeout:
    description:
      - API request timeout in seconds.
      - Can also be set with the E(KIBANA_TIMEOUT) environment variable.
    type: int
    default: 30
  retries:
    description:
      - Number of retries after the initial request for transport errors, C(408), C(429), and C(5xx) responses.
      - Can also be set with the E(KIBANA_RETRIES) environment variable.
    type: int
    default: 3
  retry_pause:
    description:
      - Base delay in seconds for jittered exponential retry backoff.
      - Can also be set with the E(KIBANA_RETRY_PAUSE) environment variable.
    type: float
    default: 1.0
  retry_status_codes:
    description:
      - HTTP status codes that trigger endpoint failover and retry.
      - Defaults to C(408), C(429), and every C(5xx) status.
    type: list
    elements: int
    default:
      - 408
      - 429
      - 500
      - 501
      - 502
      - 503
      - 504
      - 505
      - 506
      - 507
      - 508
      - 509
      - 510
      - 511
      - 512
      - 513
      - 514
      - 515
      - 516
      - 517
      - 518
      - 519
      - 520
      - 521
      - 522
      - 523
      - 524
      - 525
      - 526
      - 527
      - 528
      - 529
      - 530
      - 531
      - 532
      - 533
      - 534
      - 535
      - 536
      - 537
      - 538
      - 539
      - 540
      - 541
      - 542
      - 543
      - 544
      - 545
      - 546
      - 547
      - 548
      - 549
      - 550
      - 551
      - 552
      - 553
      - 554
      - 555
      - 556
      - 557
      - 558
      - 559
      - 560
      - 561
      - 562
      - 563
      - 564
      - 565
      - 566
      - 567
      - 568
      - 569
      - 570
      - 571
      - 572
      - 573
      - 574
      - 575
      - 576
      - 577
      - 578
      - 579
      - 580
      - 581
      - 582
      - 583
      - 584
      - 585
      - 586
      - 587
      - 588
      - 589
      - 590
      - 591
      - 592
      - 593
      - 594
      - 595
      - 596
      - 597
      - 598
      - 599
  retry_mutating_requests:
    description:
      - Whether retry and endpoint failover are allowed for mutating HTTP methods.
      - Disabled by default to prevent replaying partially completed operations.
      - Can also be set with the E(KIBANA_RETRY_MUTATING_REQUESTS) environment variable.
    type: bool
    default: false
  force_basic_auth:
    description:
      - Send legacy URL basic authentication credentials on the first request.
    type: bool
    default: false
  url_username:
    description:
      - Legacy username handled by the Ansible URL transport.
    type: str
  url_password:
    description:
      - Legacy password handled by the Ansible URL transport.
    type: str
"""
