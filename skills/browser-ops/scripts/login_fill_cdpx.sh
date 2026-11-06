#!/usr/bin/env bash
# Fill a login form from a 1Password LOGIN item straight into the page via cdpx (stdin). Never echoes a value.
# Usage: login_fill_cdpx.sh <ep> <tab-id> "<1P item title>" <user-sel> <pass-sel>
#   FIELDS=user|pass to fill only one (two-step logins). Vault: Home Servers.
set -uo pipefail
EP=$1; T=$2; ITEM=$3; US=$4; PS=$5
OP_SERVICE_ACCOUNT_TOKEN=$(cat ~/.op_service_token); export OP_SERVICE_ACCOUNT_TOKEN
J=$(op item get "$ITEM" --vault "Home Servers" --format json --reveal) || { echo "op lookup failed"; exit 1; }
get() { printf %s "$J" | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((f.get('value','') for f in d['fields'] if f.get('purpose')==sys.argv[1]),''),end='')" "$1"; }
[[ "${FIELDS:-user,pass}" == *user* ]] && get USERNAME | cdpx --ep "$EP" type "$T" --sel "$US" - | sed -E 's/value_len=[0-9]+/value_len=ok/'
sleep 1; [[ "${FIELDS:-user,pass}" == *pass* ]] && get PASSWORD | cdpx --ep "$EP" type "$T" --sel "$PS" - | sed -E 's/value_len=[0-9]+/value_len=ok/'
unset J
