#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  echo '请先按 README 完成环境安装。'
  exit 1
fi
exec .venv/bin/python -m blockstudio.app
