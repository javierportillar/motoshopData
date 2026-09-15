# Raspberry deployment

This bundle runs the shared MotoShop/MasVital API on ARM64, keeps chat history
in a persistent SQLite volume, caches both tenant DuckDB snapshots, and exposes
the API through a Cloudflare Tunnel.

## First boot

```bash
cd infra/raspberry
cp .env.example .env
# Fill secrets in .env and generate JWT_SECRET with: openssl rand -hex 32
docker compose up -d --build
chmod +x verify.sh
./verify.sh
```

The verification can take several minutes on first boot while both DuckDB
snapshots are downloaded from R2. It fails if either tenant, the LLM provider,
or durable SQLite storage is unavailable.

Configure the Cloudflare Tunnel public hostname used by the frontend
(`NEXT_PUBLIC_API_URL`) to route to `http://api:8000`. The committed frontend
currently expects `https://api.fragloesja.uk`.

## Required before connecting users

1. Confirm both `motoshop_gold.duckdb` and `masvital_gold.duckdb` exist in R2.
2. Fill the R2 credentials and at least one LLM API key.
3. Keep `AGENT_CONVERSATION_BACKEND=sqlite` on Raspberry; the named volume
   survives container restarts.
4. If document RAG is needed, apply the Supabase migration and fill the
   Supabase/embedding variables before running the indexing script.

## Operations

```bash
docker compose logs -f api
docker compose pull && docker compose up -d --build
docker compose down                 # keeps named volumes
docker compose down -v              # DANGER: deletes chat history and cache
```
