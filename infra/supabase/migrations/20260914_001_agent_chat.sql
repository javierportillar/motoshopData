-- Durable tenant-scoped Agentic RAG conversations and knowledge index.
create extension if not exists vector;

create table if not exists public.agent_conversations (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  user_id text not null,
  title text not null default 'Nueva conversación',
  status text not null default 'active' check (status in ('active','archived')),
  message_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz not null default now()
);
create index if not exists agent_conversations_owner_idx on public.agent_conversations (tenant_id, user_id, last_message_at desc);

create table if not exists public.agent_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.agent_conversations(id) on delete cascade,
  tenant_id text not null,
  user_id text not null,
  role text not null check (role in ('user','assistant','tool')),
  content text not null,
  request_id text,
  tools_used jsonb not null default '[]'::jsonb,
  sources jsonb not null default '[]'::jsonb,
  model text,
  provider text,
  tokens_input integer not null default 0,
  tokens_output integer not null default 0,
  latency_ms integer not null default 0,
  status text not null default 'success',
  error_code text,
  created_at timestamptz not null default now()
);
drop index if exists public.agent_messages_request_idx;
create unique index agent_messages_request_idx on public.agent_messages (conversation_id, request_id, role);
create index if not exists agent_messages_owner_idx on public.agent_messages (tenant_id, user_id, conversation_id, created_at);
alter table public.agent_messages add column if not exists evidence jsonb not null default '[]'::jsonb;
alter table public.agent_messages add column if not exists freshness jsonb not null default '[]'::jsonb;
alter table public.agent_messages add column if not exists entity_refs jsonb not null default '[]'::jsonb;
alter table public.agent_messages add column if not exists attachments jsonb not null default '[]'::jsonb;

create table if not exists public.rag_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source text not null,
  title text not null,
  checksum text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists rag_documents_source_idx on public.rag_documents (tenant_id, source);
create table if not exists public.rag_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.rag_documents(id) on delete cascade,
  tenant_id text not null,
  content text not null,
  chunk_index integer not null,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  search_vector tsvector generated always as (to_tsvector('spanish', coalesce(content, ''))) stored,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);
create index if not exists rag_chunks_tenant_idx on public.rag_chunks (tenant_id);
create index if not exists rag_chunks_search_idx on public.rag_chunks using gin (search_vector);
create index if not exists rag_chunks_embedding_idx on public.rag_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 50);
create table if not exists public.rag_ingestion_runs (
  id uuid primary key default gen_random_uuid(), tenant_id text not null, source text not null,
  status text not null, documents_count integer not null default 0, chunks_count integer not null default 0,
  error text, started_at timestamptz not null default now(), finished_at timestamptz
);

alter table public.agent_conversations enable row level security;
alter table public.agent_messages enable row level security;
alter table public.rag_documents enable row level security;
alter table public.rag_chunks enable row level security;
alter table public.rag_ingestion_runs enable row level security;

create or replace function public.match_rag_chunks(p_tenant_id text, p_query_embedding vector(1536), p_match_count integer)
returns table(id uuid, content text, source text, section text, similarity float)
language sql stable as $$
  select c.id, c.content, d.source, c.metadata->>'section', 1 - (c.embedding <=> p_query_embedding)
  from public.rag_chunks c join public.rag_documents d on d.id = c.document_id
  where c.tenant_id = p_tenant_id and c.embedding is not null
  order by c.embedding <=> p_query_embedding limit greatest(1, least(p_match_count, 20));
$$;

create or replace function public.search_rag_chunks(p_tenant_id text, p_query text, p_match_count integer)
returns table(id uuid, content text, source text, section text, rank float)
language sql stable as $$
  select c.id, c.content, d.source, c.metadata->>'section', ts_rank_cd(c.search_vector, websearch_to_tsquery('spanish', p_query))
  from public.rag_chunks c join public.rag_documents d on d.id = c.document_id
  where c.tenant_id = p_tenant_id and c.search_vector @@ websearch_to_tsquery('spanish', p_query)
  order by 5 desc limit greatest(1, least(p_match_count, 20));
$$;
