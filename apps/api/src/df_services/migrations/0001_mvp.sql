-- DesignForge MVP schema (single tenant). The multi-tenant target schema lives in
-- supabase/migrations/0001_init.sql; this is the subset the MVP pipeline needs.
-- Requires Postgres 13+ (gen_random_uuid is built in).

create table designs (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  status        text not null default 'uploaded'
                check (status in ('uploaded','analyzing','spec_ready','building','model_ready','failed','unsupported')),
  category      text,
  hints         jsonb not null default '{}',     -- {category?, anchors:[{dimension,value_mm}], notes?}
  current_spec_id uuid,
  status_message text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table source_images (
  id            uuid primary key default gen_random_uuid(),
  design_id     uuid not null references designs(id) on delete cascade,
  storage_key   text not null,
  sha256        char(64) not null,
  content_type  text not null,
  bytes         int not null,
  width_px      int not null,
  height_px     int not null,
  position      int not null,
  created_at    timestamptz not null default now(),
  unique (design_id, sha256)
);

create table design_specs (
  id               uuid primary key default gen_random_uuid(),
  design_id        uuid not null references designs(id) on delete cascade,
  version          int not null,
  origin           text not null check (origin in ('ai','user_edit')),
  spec             jsonb not null,                -- df_domain.FurnitureSpec
  spec_hash        char(64) not null,
  observation      jsonb,                         -- df_domain.ImageObservation (ai origin)
  field_confidence jsonb not null default '{}',
  issues           jsonb not null default '[]',
  provider         text,
  model            text,
  created_at       timestamptz not null default now(),
  unique (design_id, version)
);
alter table designs add constraint designs_current_spec_fk
  foreign key (current_spec_id) references design_specs(id) on delete set null;

-- Postgres-backed job queue: claimed with FOR UPDATE SKIP LOCKED.
create table jobs (
  id            uuid primary key default gen_random_uuid(),
  design_id     uuid not null references designs(id) on delete cascade,
  kind          text not null check (kind in ('analyze','build_model')),
  status        text not null default 'queued' check (status in ('queued','running','succeeded','failed','cancelled')),
  payload       jsonb not null default '{}',
  result        jsonb,
  error         jsonb,
  step          text,
  progress      real not null default 0,
  attempts      int not null default 0,
  max_attempts  int not null default 3,
  run_after     timestamptz not null default now(),
  locked_by     text,
  heartbeat_at  timestamptz,
  created_at    timestamptz not null default now(),
  started_at    timestamptz,
  finished_at   timestamptz
);
create index jobs_ready_idx on jobs (run_after, created_at) where status = 'queued';
create index jobs_design_idx on jobs (design_id, created_at desc);

create table job_events (
  id          bigserial primary key,
  job_id      uuid not null references jobs(id) on delete cascade,
  ts          timestamptz not null default now(),
  level       text not null default 'info' check (level in ('info','warning','error')),
  step        text,
  message     text not null,
  data        jsonb
);
create index job_events_job_idx on job_events (job_id, id);

create table artifacts (
  id           uuid primary key default gen_random_uuid(),
  design_id    uuid not null references designs(id) on delete cascade,
  spec_id      uuid references design_specs(id) on delete cascade,
  job_id       uuid references jobs(id) on delete set null,
  kind         text not null,                   -- 'glb','skp','obj','stl','png','part_graph','parts_csv','spec_json'
  name         text not null,                   -- display / download file name
  storage_key  text not null,
  bytes        bigint not null,
  sha256       char(64) not null,
  mime         text not null,
  producer     text not null,
  created_at   timestamptz not null default now()
);
create index artifacts_design_idx on artifacts (design_id, spec_id, kind);
