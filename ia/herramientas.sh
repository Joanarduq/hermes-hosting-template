#!/usr/bin/env bash
set -eu
tool=${1:-}
shift || true
case "$tool" in
  reach) exec uvx --python 3.12 --from git+https://github.com/Panniantong/Agent-Reach@c70ae6da5d39bc90e09ad2ae0575ccc89f31e284 agent-reach "$@" ;;
  scan) exec uvx --python 3.12 --from git+https://github.com/NVIDIA/SkillSpector@86d46b1721f029819020df396e8fa1c96eb83236 skillspector scan --no-llm "$@" ;;
  ponytail) repo=DietrichGebert/ponytail; rev=96608e078b2d5ea607c5c3b8b5a54d1c1fba6846; guide=skills/ponytail/SKILL.md ;;
  cine) repo=lemomo-ai/lemo-opuscar; rev=9eb7739a0fca4c6990fe966cb8b87b1930f7193a; guide=AGENTS.md ;;
  *) echo 'Uso: bash herramientas.sh {reach argumentos...|scan ruta|ponytail|cine}' >&2; exit 2 ;;
esac
# Cada usuario conserva sus propias fuentes y dependencias.
root=${XDG_CACHE_HOME:-"$HOME/.cache"}/hermes-ia
mkdir -p "$root"
dest="$root/$rev"
if [ ! -d "$dest/.git" ]; then
  tmp=$(mktemp -d "$root/preparando.XXXXXXXX")
  trap 'rm -rf -- "$tmp"' EXIT
  git -C "$tmp" init -q
  git -C "$tmp" fetch -q --depth=1 "https://github.com/$repo.git" "$rev"
  git -C "$tmp" checkout -q --detach FETCH_HEAD
  mv -T "$tmp" "$dest" || test -d "$dest/.git"
fi
test "$(git -C "$dest" rev-parse HEAD)" = "$rev"
test -f "$dest/$guide"
echo "$dest/$guide"
