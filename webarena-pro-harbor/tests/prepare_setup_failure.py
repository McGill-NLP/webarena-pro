"""Export a native trial whose browser fails before its health endpoint binds."""

import sys
from pathlib import Path

import yaml
from prepare_smoke import prepare

from webarena_pro_harbor.export import TOKEN, write


def prepare_failure(output):
    root = prepare(output)
    path = root / "environment/docker-compose.yaml"
    compose = yaml.safe_load(path.read_text())
    # File loading fails before Core evidence/session initialization. A secret
    # embedded in the error's path exercises redaction through the real runner.
    compose["services"]["webarena"]["command"][-1] = "/opt/webarena/missing?token=" + TOKEN
    write(path, yaml.safe_dump(compose, sort_keys=False))
    return root


if __name__ == "__main__":
    print(prepare_failure(Path(sys.argv[1])))
