#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
docker compose config --quiet
docker compose ps
running_services="$(docker compose ps --status running --services)"
printf '%s\n' "$running_services" | grep -qx api
printf '%s\n' "$running_services" | grep -qx cloudflared
curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null

# Trigger each tenant's R2 bootstrap and wait until both snapshots are ready.
for tenant in motoshop masvital; do
  attempts=0
  until curl --fail --silent --show-error \
    "http://127.0.0.1:8000/api/health/ready?tenant=${tenant}" \
    | grep -q '"ready":true'; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      echo "ERROR: ${tenant} DuckDB was not ready after 5 minutes" >&2
      exit 1
    fi
    sleep 5
  done
done

docker compose exec -T api python - <<'PY'
from motoshop_api.llm.client import LLMClient
from motoshop_api.llm.conversations.repository import get_conversation_repository
from motoshop_api.llm.tools import ToolExecutor
from motoshop_api.tenants import get_all_tenants, load_tenants

load_tenants('/app/tenants.yaml')
assert set(get_all_tenants()) == {'motoshop', 'masvital'}, 'tenant configuration is incomplete'
client = LLMClient()
assert client.configured_backends, 'no LLM provider key is configured'
reply = client.complete_with_tools(
    [{'role': 'user', 'content': 'Reply with only OK. Do not call tools.'}],
    [{
        'type': 'function',
        'function': {
            'name': 'health_probe',
            'description': 'Unused deployment health probe.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    }],
    max_tokens=8,
)
assert reply['text'].strip() or reply['tool_calls'], 'LLM provider returned an empty response'
client.close()
for tenant in ('motoshop', 'masvital'):
    freshness = ToolExecutor(tenant=tenant).get_data_freshness()
    assert freshness['fecha_maxima'], f'{tenant} DuckDB has no business date'
repository = get_conversation_repository()
assert repository.__class__.__name__ == 'SQLiteConversationRepository'
print('Agent prerequisites: OK')
PY

echo "Raspberry API health check: OK"
