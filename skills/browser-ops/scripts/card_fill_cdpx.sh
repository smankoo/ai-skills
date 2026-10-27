#!/usr/bin/env bash
# Fill a card form from 1Password straight into the page via cdpx (stdin). Never echoes a value.
# Usage: card_fill_cdpx.sh <tab-id> <card-sel> <expiry-sel> <cvv-sel> [expiry-format MMYY|MM/YY]
set -uo pipefail
T=$1; CS=$2; ES=$3; VS=$4; FMT=${5:-MM/YY}
OP_SERVICE_ACCOUNT_TOKEN=$(cat ~/.op_service_token) || exit 1
export OP_SERVICE_ACCOUNT_TOKEN
ITEM="Wealthsimple Credit Card"; V="Home Servers"
J=$(op item get "$ITEM" --vault "$V" --format json --reveal)
get() { printf %s "$J" | python3 -c "import json,sys;d=json.load(sys.stdin);print(next(f.get('value','') for f in d['fields'] if f.get('id')==sys.argv[1]),end='')" "$1"; }
exp_fmt() { python3 -c "
import sys; v=sys.stdin.read().strip().replace('/','')
y,m=(v[:4],v[4:]) if len(v)==6 else (v[2:],v[:2])
mm=m.zfill(2); yy=y[-2:]
print(mm+('/' if sys.argv[1]=='MM/YY' else '')+yy,end='')" "$FMT"; }
[[ "${FIELDS:-num,exp,cvv}" == *num* ]] && get ccnum | cdpx type "$T" --sel "$CS" - | sed -E 's/value_len=[0-9]+/value_len=ok/'
sleep 1; [[ "${FIELDS:-num,exp,cvv}" == *exp* ]] && get expiry | exp_fmt | cdpx type "$T" --sel "$ES" - | sed -E 's/value_len=[0-9]+/value_len=ok/'
sleep 1; [[ "${FIELDS:-num,exp,cvv}" == *cvv* ]] && get cvv | cdpx type "$T" --sel "$VS" - | sed -E 's/value_len=[0-9]+/value_len=ok/'
unset J
