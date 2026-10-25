-- DesignForge — initial schema
-- Conventions: uuid PKs (gen_random_uuid), org_id on every tenant table, timestamptz,
-- dimensions in integer millimetres, money in integer minor units + currency.

create extension if not exists pgcrypto;
create extension if not exists citext;

-- ─────────────────────────────────────────────────────────────────────────────
-- Tenancy helpers
-- Clerk is configured as a Supabase third-party auth provider. The Clerk session
-- token template adds a custom claim "org_id" = Clerk organization id (org_...).
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function public.current_clerk_org_id() returns text
language sql stable as $$ select nullif(auth.jwt() ->> 'org_id', '') $$;

create or replace function public.current_org_id() returns uuid
language sql stable security definer set search_path = public as $$
  select id from organizations where clerk_org_id = public.current_clerk_org_id()
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────────────────────────────────────────
create type member_role        as enum ('owner','admin','designer','shop','viewer');
create type plan_tier          as enum ('free','studio','workshop','enterprise');
create type furniture_category as enum (
  'wardrobe','base_cabinet','wall_cabinet','tall_cabinet','kitchen_run','tv_unit',
  'bookcase','sideboard','chest_of_drawers','desk','bed_frame','shoe_cabinet','vanity','other');
create type version_status     as enum ('draft','in_review','approved','superseded','archived');
create type issue_severity     as enum ('info','warning','error');
create type run_status         as enum ('created','running','awaiting_review','completed','failed','cancelled');
create type step_status        as enum ('pending','running','succeeded','failed','skipped');
create type step_name          as enum ('ingest','perceive','draft_spec','validate_spec','generate_parts',
                                        'build_geometry','compute_mfg','render_drawings','package');
create type artifact_kind      as enum ('source_image','skp','obj','stl','dxf_3d','gltf','scene_png',
                                        'drawing_pdf','drawing_dxf','drawing_svg','cutlist_csv','cutlist_xlsx',
                                        'bom_csv','bom_xlsx','nest_pdf','cnc_dxf','cnc_mpr','cnc_bpp','labels_pdf','package_zip');
create type grain_dir          as enum ('none','length','width');
create type material_kind      as enum ('sheet','solid','edge_band','glass','metal','other');
create type op_kind            as enum ('drill','groove','rebate','pocket','cutout','edge_profile','saw_cut');
create type geometry_job_status as enum ('queued','claimed','running','succeeded','failed','timed_out');

-- ─────────────────────────────────────────────────────────────────────────────
-- Identity & Tenancy
-- ─────────────────────────────────────────────────────────────────────────────
create table organizations (
  id            uuid primary key default gen_random_uuid(),
  clerk_org_id  text unique not null,
  name          text not null,
  plan          plan_tier not null default 'free',
  units_display text not null default 'mm' check (units_display in ('mm','in')),
  default_rule_pack_id uuid,        -- fk added below
  created_at    timestamptz not null default now()
);

create table members (
  org_id        uuid not null references organizations(id) on delete cascade,
  clerk_user_id text not null,
  email         citext not null,
  role          member_role not null default 'designer',
  created_at    timestamptz not null default now(),
  primary key (org_id, clerk_user_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Catalog (org_id null = global DesignForge default catalog)
-- ─────────────────────────────────────────────────────────────────────────────
create table materials (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid references organizations(id) on delete cascade,
  code          text not null,                  -- e.g. 'MFC18-W1000' or supplier SKU
  name          text not null,                  -- 'Egger W1000 ST9 Premium White 18mm'
  kind          material_kind not null,
  core          text,                           -- 'MDF','PB','PLY','HDF','OAK' …
  thickness_mm  int,                            -- sheets/edge bands
  grain         grain_dir not null default 'none',
  density_kg_m3 int,
  price_minor   bigint,                         -- per m² (sheet), per m (band), per unit
  currency      char(3) default 'EUR',
  appearance    jsonb not null default '{}',    -- {color:'#f4f4f1', texture_url, sketchup_material_name}
  is_active     boolean not null default true,
  unique (org_id, code)
);

create table sheet_stock (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid references organizations(id) on delete cascade,
  material_id   uuid not null references materials(id),
  length_mm     int not null,                   -- 2800
  width_mm      int not null,                   -- 2070
  trim_mm       int not null default 10,
  qty_on_hand   int,
  price_minor   bigint
);

create table hardware_items (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid references organizations(id) on delete cascade,
  code          text not null,                  -- 'BLUM-71B3550'
  family        text not null,                  -- 'hinge','slide','connector','handle','leg','rail','shelf_pin'
  brand         text,
  name          text not null,
  params        jsonb not null default '{}',    -- {opening_angle:110, cup_d:35, boring_distance:[3,6]} | {length:500, load_kg:30}
  drilling      jsonb not null default '[]',    -- drilling pattern template (part-local), see df_domain.HardwareDrilling
  price_minor   bigint,
  currency      char(3) default 'EUR',
  unique (org_id, code)
);

create table rule_packs (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid references organizations(id) on delete cascade,
  name          text not null,
  version       int not null,
  rules         jsonb not null,                 -- validated by df_rules.RulePackModel
  frozen        boolean not null default false, -- true once any approved version references it
  created_at    timestamptz not null default now(),
  unique (org_id, name, version)
);
alter table organizations add constraint organizations_default_rule_pack_fk
  foreign key (default_rule_pack_id) references rule_packs(id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Design core
-- ─────────────────────────────────────────────────────────────────────────────
create table projects (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  name          text not null,
  client_name   text,
  site_address  text,
  created_by    text not null,
  created_at    timestamptz not null default now(),
  archived_at   timestamptz
);

create table designs (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  project_id    uuid not null references projects(id) on delete cascade,
  name          text not null,
  category      furniture_category,             -- known after perception
  current_version_id uuid,                      -- fk added below
  created_by    text not null,
  created_at    timestamptz not null default now()
);

create table source_images (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  design_id     uuid not null references designs(id) on delete cascade,
  storage_path  text not null,
  sha256        char(64) not null,
  phash         bigint,                         -- perceptual hash, dedupe
  width_px      int, height_px int,
  role          text not null default 'reference' check (role in ('reference','detail','site_photo','sketch')),
  user_notes    text,                           -- "the white one on the left, ignore the bed"
  accepted      boolean,                        -- ingestion relevance check
  rejected_reason text,
  created_at    timestamptz not null default now(),
  unique (design_id, sha256)
);

create table analysis_runs (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  design_id     uuid not null references designs(id) on delete cascade,
  stage         text not null check (stage in ('perception','spec_draft')),
  provider      text not null,                  -- 'openai','anthropic','ensemble'
  model         text not null,                  -- exact model id
  prompt_version text not null,                 -- 'perception@7'
  input_tokens  int, output_tokens int, cost_micro_usd bigint,
  latency_ms    int,
  raw_response  jsonb,                          -- for audits/evals; strip if PII concerns
  trace_id      text,                           -- Langfuse
  created_at    timestamptz not null default now()
);

create table image_observations (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizations(id) on delete cascade,
  source_image_id  uuid not null references source_images(id) on delete cascade,
  analysis_run_id  uuid not null references analysis_runs(id) on delete cascade,
  observation      jsonb not null,              -- df_domain.ImageObservation
  confidence       real not null check (confidence between 0 and 1),
  created_at       timestamptz not null default now()
);

create table design_versions (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references organizations(id) on delete cascade,
  design_id         uuid not null references designs(id) on delete cascade,
  version_no        int not null,
  parent_version_id uuid references design_versions(id),
  status            version_status not null default 'draft',
  spec              jsonb not null,             -- df_domain.FurnitureSpec
  spec_hash         char(64) not null,
  field_confidence  jsonb not null default '{}',-- {"overall.width": {"value":0.62,"source":"anchor"}}
  rule_pack_id      uuid not null references rule_packs(id),
  generator_version text,                       -- set at generate_parts: 'df_parametric@0.4.2'
  graph_hash        char(64),
  origin            text not null default 'ai' check (origin in ('ai','user_edit','duplicate','api')),
  approved_by       text,
  approved_at       timestamptz,
  created_by        text not null,
  created_at        timestamptz not null default now(),
  unique (design_id, version_no)
);
alter table designs add constraint designs_current_version_fk
  foreign key (current_version_id) references design_versions(id);
create unique index one_draft_per_design on design_versions(design_id) where status = 'draft';

-- Freeze approved versions.
create or replace function forbid_frozen_version_change() returns trigger language plpgsql as $$
begin
  if old.status = 'approved' and (
       new.spec is distinct from old.spec or new.rule_pack_id is distinct from old.rule_pack_id
    or (old.graph_hash is not null and new.graph_hash is distinct from old.graph_hash)) then
    raise exception 'design_version % is approved and immutable', old.id;
  end if;
  return new;
end $$;
create trigger trg_freeze_version before update on design_versions
  for each row execute function forbid_frozen_version_change();

create table spec_issues (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  rule_code     text not null,                  -- 'SHELF_SPAN_EXCEEDED'
  severity      issue_severity not null,
  path          text not null,                  -- JSON pointer into spec: '/sections/1/compartments/0'
  message       text not null,
  suggestion    jsonb,                          -- JSON Patch the UI can apply with one click
  created_at    timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- PartGraph (canonical JSONB + denormalised rows)
-- ─────────────────────────────────────────────────────────────────────────────
create table part_graphs (
  version_id        uuid primary key references design_versions(id) on delete cascade,
  org_id            uuid not null references organizations(id) on delete cascade,
  graph             jsonb not null,             -- df_domain.PartGraph
  graph_hash        char(64) not null,
  generator_version text not null,
  part_count        int not null,
  bbox_mm           int[] not null,             -- [w,h,d]
  created_at        timestamptz not null default now()
);

create table parts (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  part_key      text not null,                  -- stable semantic key: 's2.drawer1.side_l'
  role          text not null,                  -- 'gable','top','bottom','back','shelf','divider','door','drawer_front', …
  label         text not null,                  -- human: 'Drawer side L (S2-D1)'
  material_id   uuid not null references materials(id),
  length_mm     int not null,                   -- finished, along grain
  width_mm      int not null,
  thickness_mm  int not null,
  cut_length_mm int not null,                   -- after edge-band deduction
  cut_width_mm  int not null,
  grain         grain_dir not null,
  edge_band     jsonb not null default '{}',    -- {"L1":"EB-W1000-1.0","L2":null,"W1":...,"W2":...}
  transform     jsonb not null,                 -- 4x4 column-major, mm; part-local → assembly
  assembly_path text not null,                  -- 'carcass/section_2/drawer_1'
  qty           int not null default 1,
  unique (version_id, part_key)
);
create index parts_material_idx on parts(material_id);

create table part_operations (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  part_id       uuid not null references parts(id) on delete cascade,
  kind          op_kind not null,
  face          text not null check (face in ('top','bottom','front','back','left','right')),
  params        jsonb not null,                 -- {x,y,diameter,depth} | {x1,y1,x2,y2,width,depth} …
  tool_hint     text,                           -- 'D5','D8','D35','SAW4' (mapped by CNC post)
  source        text not null                   -- 'hardware:BLUM-71B3550#3' | 'joint:minifix' | 'system32'
);

create table hardware_placements (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  hardware_id   uuid not null references hardware_items(id),
  qty           int not null,
  attached_to   text[] not null,                -- part_keys
  params        jsonb not null default '{}'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Manufacturing & Documentation outputs
-- ─────────────────────────────────────────────────────────────────────────────
create table cutlist_items (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  line_no       int not null,
  part_keys     text[] not null,                -- identical parts grouped
  material_id   uuid not null references materials(id),
  cut_length_mm int not null, cut_width_mm int not null, thickness_mm int not null,
  qty           int not null,
  grain         grain_dir not null,
  edge_band     jsonb not null,
  has_machining boolean not null,
  label_code    text not null                   -- printed on part label / barcode
);

create table bom_lines (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  category      text not null check (category in ('sheet','edge_band','hardware','consumable','labour')),
  ref_id        uuid,                           -- material_id or hardware_id
  description   text not null,
  qty           numeric(12,3) not null,
  unit          text not null,                  -- 'sheet','m2','m','pcs','h'
  unit_price_minor bigint,
  total_minor   bigint,
  currency      char(3)
);

create table nest_layouts (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  material_id   uuid not null references materials(id),
  sheet_stock_id uuid references sheet_stock(id),
  sheet_index   int not null,
  placements    jsonb not null,                 -- [{part_key,x,y,rotated}]
  yield_pct     real not null,
  algorithm     text not null                   -- 'guillotine-maxrects@1'
);

create table drawing_sheets (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  sheet_no      int not null,
  kind          text not null,                  -- 'general_arrangement','elevation','section','part','assembly','hardware','nesting'
  title         text not null,
  paper         text not null default 'A3',
  artifact_id   uuid                            -- fk below
);

create table artifacts (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  design_id     uuid not null references designs(id) on delete cascade,
  version_id    uuid references design_versions(id) on delete cascade,
  kind          artifact_kind not null,
  storage_path  text not null,
  sha256        char(64) not null,
  bytes         bigint not null,
  mime          text not null,
  producer      text not null,                  -- 'df_drawings@0.3.1' | 'sketchup-bridge@0.2.0/SU2026'
  meta          jsonb not null default '{}',
  created_at    timestamptz not null default now()
);
create index artifacts_version_idx on artifacts(version_id, kind);
alter table drawing_sheets add constraint drawing_sheets_artifact_fk foreign key (artifact_id) references artifacts(id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Orchestration
-- ─────────────────────────────────────────────────────────────────────────────
create table pipeline_runs (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  design_id     uuid not null references designs(id) on delete cascade,
  version_id    uuid references design_versions(id),
  kind          text not null check (kind in ('from_images','regenerate','exports_only')),
  status        run_status not null default 'created',
  options       jsonb not null default '{}',    -- {skip_geometry:false, cnc_dialect:'dxf_generic'}
  error         jsonb,
  started_at    timestamptz, finished_at timestamptz,
  created_by    text not null,
  created_at    timestamptz not null default now()
);
create unique index one_active_run_per_version on pipeline_runs(version_id)
  where status in ('created','running');

create table pipeline_steps (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  run_id        uuid not null references pipeline_runs(id) on delete cascade,
  name          step_name not null,
  status        step_status not null default 'pending',
  attempt       int not null default 0,
  input_hash    char(64),
  celery_task_id text,
  progress      real,                           -- 0..1 for long steps
  error         jsonb,
  started_at    timestamptz, finished_at timestamptz,
  unique (run_id, name)
);

create table domain_events (                     -- transactional outbox
  id            bigserial primary key,
  org_id        uuid not null,
  aggregate     text not null,                  -- 'pipeline_run'
  aggregate_id  uuid not null,
  type          text not null,                  -- 'spec.drafted'
  payload       jsonb not null,
  created_at    timestamptz not null default now(),
  published_at  timestamptz
);
create index domain_events_unpublished on domain_events(id) where published_at is null;
create or replace function notify_domain_event() returns trigger language plpgsql as $$
begin perform pg_notify('domain_events', new.id::text); return new; end $$;
create trigger trg_notify_domain_event after insert on domain_events
  for each row execute function notify_domain_event();

-- ─────────────────────────────────────────────────────────────────────────────
-- Geometry farm
-- ─────────────────────────────────────────────────────────────────────────────
create table geometry_nodes (
  id              text primary key,             -- 'gn-euw-01'
  sketchup_version text not null,               -- '2026.0.x'
  bridge_version  text not null,
  status          text not null check (status in ('healthy','busy','draining','unhealthy','offline')),
  last_heartbeat  timestamptz not null,
  jobs_completed  int not null default 0,
  meta            jsonb not null default '{}'
);

create table geometry_jobs (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  run_id        uuid references pipeline_runs(id) on delete cascade,
  version_id    uuid not null references design_versions(id) on delete cascade,
  graph_hash    char(64) not null,
  engine        text not null,                  -- 'sketchup_mcp' | 'sketchup_sdk' | 'gltf'
  exports       text[] not null,                -- {'skp','obj','stl','scenes'}
  status        geometry_job_status not null default 'queued',
  node_id       text references geometry_nodes(id),
  attempt       int not null default 0,
  duration_ms   int,
  error         jsonb,
  created_at    timestamptz not null default now()
);
-- Cache lookup: identical graph + bridge version ⇒ reuse artifacts.
create index geometry_jobs_cache on geometry_jobs(graph_hash, engine) where status = 'succeeded';

-- ─────────────────────────────────────────────────────────────────────────────
-- Billing / usage
-- ─────────────────────────────────────────────────────────────────────────────
create table usage_events (
  id            bigserial primary key,
  org_id        uuid not null references organizations(id) on delete cascade,
  kind          text not null,                  -- 'perception','spec_draft','geometry','package'
  credits       int not null,
  ref_id        uuid,
  created_at    timestamptz not null default now()
);

create table credit_ledger (
  id            bigserial primary key,
  org_id        uuid not null references organizations(id) on delete cascade,
  delta         int not null,
  reason        text not null,                  -- 'monthly_grant','purchase','usage','refund'
  ref           text,
  created_at    timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Row Level Security: tenant isolation for direct client access (Realtime, Storage).
-- The API/workers use the service role and enforce org scoping in repositories.
-- ─────────────────────────────────────────────────────────────────────────────
do $$
declare t text;
begin
  foreach t in array array[
    'projects','designs','source_images','analysis_runs','image_observations','design_versions',
    'spec_issues','part_graphs','parts','part_operations','hardware_placements','cutlist_items',
    'bom_lines','nest_layouts','drawing_sheets','artifacts','pipeline_runs','pipeline_steps',
    'geometry_jobs','usage_events','credit_ledger']
  loop
    execute format('alter table %I enable row level security', t);
    execute format($p$create policy tenant_read on %I for select using (org_id = public.current_org_id())$p$, t);
  end loop;
end $$;

-- Catalog: global rows (org_id is null) readable by everyone, org rows by members.
alter table materials      enable row level security;
alter table hardware_items enable row level security;
alter table sheet_stock    enable row level security;
alter table rule_packs     enable row level security;
create policy catalog_read on materials      for select using (org_id is null or org_id = public.current_org_id());
create policy catalog_read on hardware_items for select using (org_id is null or org_id = public.current_org_id());
create policy catalog_read on sheet_stock    for select using (org_id is null or org_id = public.current_org_id());
create policy catalog_read on rule_packs     for select using (org_id is null or org_id = public.current_org_id());

-- Writes go exclusively through the API (service role); no insert/update policies for clients.
