#!/usr/bin/env bash
# Integration test on the GitHub Linux runner, using synthetic tenants only.
set -euo pipefail
umask 077
binary=$(realpath "$1")
work=$(mktemp -d)
image="hermes-tenant-test:$(basename "$work" | tr '[:upper:]' '[:lower:]')"
cleanup() {
  docker image rm "$image" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
mkdir "$work/build"
install -m755 "$binary" "$work/build/rclone"
printf 'FROM scratch\nCOPY rclone /rclone\nENTRYPOINT ["/rclone"]\n' > "$work/build/Dockerfile"
docker build -q -t "$image" "$work/build" >/dev/null

client() {
  local tenant=$1
  shift
  docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
    --memory 256m --cpus 1 --pids-limit 64 \
    -v "$work/$tenant:/client" "$image" --config /client/rclone.conf "$@"
}
for tenant in alice bob; do
  mkdir -p "$work/$tenant/store"
  secret=$(openssl rand -hex 32 | "$binary" obscure -)
  printf '[vault]\ntype = crypt\nremote = /client/store\npassword = %s\n' "$secret" > "$work/$tenant/rclone.conf"
  head -c 1048576 /dev/urandom > "$work/$tenant/input"
done

# Plaintext quota for immutable, unique object names in this disposable pilot.
python3 - "$work" <<'PY'
import pathlib, sqlite3, sys
db = sqlite3.connect(pathlib.Path(sys.argv[1]) / 'quota.db')
with db:
    db.execute('CREATE TABLE plans (tenant TEXT PRIMARY KEY, capacity INTEGER NOT NULL)')
    db.execute('CREATE TABLE reservations (tenant TEXT, object TEXT, bytes INTEGER, PRIMARY KEY(tenant, object))')
    db.executemany('INSERT INTO plans VALUES (?, ?)', [('alice', 2**20), ('bob', 2**20)])
PY
upload() {
  local tenant=$1 object=$2
  python3 - "$work" "$tenant" "$object" <<'PY' || return $?
import pathlib, sqlite3, sys
root, tenant, obj = sys.argv[1:]
size = (pathlib.Path(root) / tenant / 'input').stat().st_size
with sqlite3.connect(pathlib.Path(root) / 'quota.db', timeout=15) as db:
    db.execute('BEGIN IMMEDIATE')
    limit, = db.execute('SELECT capacity FROM plans WHERE tenant=?', (tenant,)).fetchone()
    used, = db.execute('SELECT coalesce(sum(bytes),0) FROM reservations WHERE tenant=?', (tenant,)).fetchone()
    if size > limit - used:
        sys.exit(42)
    db.execute('INSERT INTO reservations VALUES (?,?,?)', (tenant, obj, size))
PY
  client "$tenant" copyto /client/input "vault:$object"
}
for tenant in alice bob; do
  upload "$tenant" probe1 & first=$!
  upload "$tenant" probe2 & second=$!
  a=0; b=0
  wait "$first" || a=$?
  wait "$second" || b=$?
  case "$a,$b" in
    0,42) object=probe1 ;;
    42,0) object=probe2 ;;
    *) echo "Unexpected upload results for $tenant: $a,$b" >&2; exit 1 ;;
  esac
  client "$tenant" copyto "vault:$object" /client/restored
  cmp "$work/$tenant/input" "$work/$tenant/restored"
  [[ $(find "$work/$tenant/store" -type f | wc -l) -eq 1 ]]
done

for tenant in alice bob; do
  other=alice
  [[ $tenant == alice ]] && other=bob
  # The other tenant's mounted data and host path must be invisible.
  if client "$tenant" copyto "$work/$other/input" /client/cross-read; then exit 1; fi
  # Present a copy of the foreign ciphertext under a locally valid encrypted
  # filename. This tests content authentication independently of filename hiding.
  foreign=$(find "$work/$other/store" -type f -print -quit)
  own=$(find "$work/$tenant/store" -type f -print -quit)
  mkdir "$work/$tenant/foreign"
  cp "$foreign" "$work/$tenant/foreign/$(basename "$own")"
  sed 's@/client/store@/client/foreign@' "$work/$tenant/rclone.conf" > "$work/$tenant/foreign.conf"
  object=probe1
  python3 -c 'import sqlite3,sys; sys.exit(not sqlite3.connect(sys.argv[1]).execute("select 1 from reservations where tenant=? and object=?", (sys.argv[2],"probe1")).fetchone())' "$work/quota.db" "$tenant" || object=probe2
  if client "$tenant" --config /client/foreign.conf --retries 1 --low-level-retries 1 copyto "vault:$object" /client/foreign-result 2>"$work/error"; then exit 1; fi
  grep -Eiq 'failed to authenticate|authentication failed|bad block' "$work/error"
done
echo "Two tenants restored their own bytes. Each admitted one concurrent upload and rejected the other at quota. Both foreign keys failed authentication."
