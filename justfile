# Override these for local CI runs, for example: ACT_EVENT=pull_request just act-integration.
act_image := env_var_or_default("ACT_IMAGE", "ghcr.io/catthehacker/ubuntu:full-22.04")
act_event := env_var_or_default("ACT_EVENT", "push")

init:
    uv venv --allow-existing --python 3.11
    uv pip install --python .venv/bin/python \
        "ansible-core>=2.19.5" \
        "ansible-lint>=26.1.1" \
        "coverage==7.6.1" \
        "ruff>=0.14.13" \
        "molecule>=26.6.0" \
        "molecule-plugins[docker]>=26.7.15" \
        "antsibull-core>=3.5.0" \
        "antsibull-docs>=2.24.0"
    .venv/bin/ansible-galaxy collection install \
        -r extensions/molecule/kibana/collections.yml \
        --force

install:
    .venv/bin/ansible-galaxy collection install . --force

# Activate the Elasticsearch trial license for local Fleet/API testing.
# The recipe intentionally fails when the cluster cannot start a trial.
activate-trial:
    #!/usr/bin/env bash
    set -euo pipefail
    elasticsearch_url="${ELASTICSEARCH_URL:-http://localhost:9200}"
    elasticsearch_username="${ELASTICSEARCH_USERNAME:-elastic}"
    elasticsearch_password="${ELASTICSEARCH_PASSWORD:-changeme}"
    response_file="$(mktemp)"
    trap 'rm -f "$response_file"' EXIT
    http_code="$(curl --silent --show-error --user "$elasticsearch_username:$elasticsearch_password" --header 'Content-Type: application/json' --request POST --output "$response_file" --write-out '%{http_code}' "${elasticsearch_url%/}/_license/start_trial?acknowledge=true")"
    if [[ "$http_code" != 200 ]]; then
        echo "Unable to activate the Elasticsearch trial license (HTTP $http_code)." >&2
        exit 1
    fi
    if ! grep --quiet --extended-regexp '"trial_was_started"[[:space:]]*:[[:space:]]*true' "$response_file"; then
        echo "Elasticsearch did not confirm trial license activation." >&2
        exit 1
    fi
    echo "Elasticsearch trial license activated."

molecule:
    .venv/bin/ansible-galaxy collection install . --force
    cd extensions && PATH="{{ justfile_directory() }}/.venv/bin:$PATH" molecule test --scenario-name kibana

ruff:
    .venv/bin/ruff check .

sanity:
    .venv/bin/ansible-test sanity --coverage
    .venv/bin/ansible-test coverage report --include 'plugins/*'

integration:
    .venv/bin/ansible-test integration --coverage
    .venv/bin/ansible-test coverage report --include 'plugins/*'

# Run GitHub Actions locally with Docker host networking for the Stack services.
act-integration:
    act {{ act_event }} -W .github/workflows/ansible-test-integration.yml -P ubuntu-latest={{ act_image }} --container-options="--privileged --network host"

act-unit:
    act {{ act_event }} -W .github/workflows/ansible-test-unit.yml -P ubuntu-latest={{ act_image }} --container-options="--privileged --network host"

act-sanity:
    act {{ act_event }} -W .github/workflows/ansible-test-sanity.yml -P ubuntu-latest={{ act_image }} --container-options="--privileged --network host"

act-molecule:
    act {{ act_event }} -W .github/workflows/molecule.yml -P ubuntu-latest={{ act_image }} --container-options="--privileged --network host"

act-ci: act-unit act-sanity act-integration act-molecule

# Parse workflows and matrix expressions without executing jobs.
act-dry-run:
    act {{ act_event }} -W .github/workflows/ansible-test-unit.yml -W .github/workflows/ansible-test-sanity.yml -W .github/workflows/ansible-test-integration.yml -W .github/workflows/molecule.yml -P ubuntu-latest={{ act_image }} --container-options="--privileged --network host" --dryrun

docs:
    .venv/bin/ansible-galaxy collection install . --force
    mkdir -p .build/docs
    .venv/bin/antsibull-docs sphinx-init --use-current --dest-dir .build/docs zupersero.kibana
    uv pip install --python .venv/bin/python -r .build/docs/requirements.txt
    cd .build/docs && PATH="{{ justfile_directory() }}/.venv/bin:$PATH" ./build.sh
    cp docs/environment_variables.rst .build/docs/rst/collections/environment_variables.rst
    cd .build/docs && PATH="{{ justfile_directory() }}/.venv/bin:$PATH" sphinx-build -M html rst build -c . -W --keep-going
    python3 -m http.server --directory .build/docs/build/html
