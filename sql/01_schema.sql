-- Bitemporal store for SEC EDGAR XBRL "company facts".
--
-- Every number a company reports has TWO time axes:
--   valid time        = the period the number describes        (period_start .. period_end)
--   transaction time  = when the market could first see it     (filed, the filing date)
-- A later filing can restate an earlier period. We never overwrite: each report of a fact is
-- its own immutable row, keyed by the filing (accn) that carried it. "What did we know on
-- date D?" is then a query, not a backup restore.
--
-- Invariants live in the database, not in the loader:
--   1. a given filing reports a given (company, tag, unit, period) at most once  (unique key)
--   2. rows are append-only: no UPDATE, DELETE or TRUNCATE (corrections arrive as new filings)
--
-- Deliberately NOT enforced as constraints: date sanity (filed >= period_end, period length).
-- Real filings violate them, and rejecting those rows would hide exactly the data we want to
-- study. They are monitored in checks.sql instead.

create table company (
    cik          bigint primary key,
    entity_name  text   not null
);

create table fact (
    fact_id        bigserial primary key,
    cik            bigint  not null references company (cik),
    taxonomy       text    not null,            -- us-gaap, dei, ...
    tag            text    not null,            -- XBRL concept, e.g. NetIncomeLoss
    unit           text    not null,            -- USD, shares, USD/shares, ...
    period_start   date,                        -- NULL for point-in-time (instant) concepts
    period_end     date    not null,            -- valid time
    value          numeric not null,
    accn           text    not null,            -- accession number of the reporting filing
    form           text    not null,            -- 10-K, 10-Q, ...
    filed          date    not null,            -- transaction time
    fiscal_year    int,                         -- NB: describes the FILING, not this period
    fiscal_period  text,                        -- FY, Q1, Q2, Q3 -- same caveat
    frame          text,                        -- SEC's calendarised period label, if assigned
    constraint fact_natural_key
        unique nulls not distinct (cik, taxonomy, tag, unit, period_start, period_end, accn)
);

create index fact_lookup on fact (cik, tag, unit, period_end);
create index fact_filed  on fact (filed);

-- ---- invariant 2: append-only -----------------------------------------------------------
create or replace function block_mutation() returns trigger as $$
begin
    raise exception 'fact is append-only: % not allowed (a correction arrives as a new filing)', tg_op;
end;
$$ language plpgsql;

create trigger fact_no_update_delete
    before update or delete on fact
    for each row execute function block_mutation();

create trigger fact_no_truncate
    before truncate on fact
    for each statement execute function block_mutation();
