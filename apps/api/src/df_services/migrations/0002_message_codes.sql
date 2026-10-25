-- Machine-readable message codes so the UI can render every server message in the user's language.
-- The English text columns stay as the fallback and for logs.

alter table job_events add column code text;
alter table job_events add column params jsonb not null default '{}';

alter table designs add column status_code text;
alter table designs add column status_params jsonb not null default '{}';

-- Structured spec notes: [{code, params, text}] (spec.notes keeps the English text).
alter table design_specs add column notes_detail jsonb not null default '[]';
