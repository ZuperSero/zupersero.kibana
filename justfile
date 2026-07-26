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

docs:
    .venv/bin/ansible-galaxy collection install . --force
    mkdir -p .build/docs
    .venv/bin/antsibull-docs sphinx-init --use-current --dest-dir .build/docs zupersero.kibana
    uv pip install --python .venv/bin/python -r .build/docs/requirements.txt
    cd .build/docs && PATH="{{ justfile_directory() }}/.venv/bin:$PATH" ./build.sh
