FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Codex uses npm. Drop the inherited Yarn apt source before installing features.
RUN find /etc/apt -name '*.list' -exec sed -i '\|dl\.yarnpkg\.com/debian|d' {} +
