#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name 'PostStudio' --osx-bundle-identifier studio.post.workbench --paths . --collect-submodules imagecodecs --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml scripts/run.py
