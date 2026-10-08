#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor
# Dependencies are separate checkouts. Never modify upstream tracked files.
for repo in k1-mp-ecowalk-public k1-mp-ecowalk-teleop; do
  if [[ ! -d "vendor/$repo" ]]; then
    git clone "https://github.com/Takeyuki-K/$repo.git" "vendor/$repo"
  fi
done
git -C vendor/k1-mp-ecowalk-public checkout --detach 04b1c0fded94dcde76411e6bd9d914a56d41102a
git -C vendor/k1-mp-ecowalk-teleop checkout --detach a5ea3dbf4f97501c18ff090f86ff4cd413f6aaea
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -e '.[test]'
