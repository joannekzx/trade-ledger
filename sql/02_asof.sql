-- Point-in-time access to the fact table.

-- facts_as_of(D): for every (company, tag, unit, period), the value as it was known on date D,
-- i.e. from the latest filing made on or before D. Periods whose first filing is after D do not
-- appear at all -- they did not exist yet as far as the market knew.
-- Ties (two filings on the same day, e.g. a 10-K and a 10-K/A) break on accession number, which
-- increases with filing order within a filer-year.
create or replace function facts_as_of(p_known date)
returns table (
    cik bigint, taxonomy text, tag text, unit text,
    period_start date, period_end date,
    value numeric, accn text, form text, filed date
)
language sql stable as $$
    select distinct on (f.cik, f.taxonomy, f.tag, f.unit, f.period_start, f.period_end)
           f.cik, f.taxonomy, f.tag, f.unit, f.period_start, f.period_end,
           f.value, f.accn, f.form, f.filed
    from fact f
    where f.filed <= p_known
    order by f.cik, f.taxonomy, f.tag, f.unit, f.period_start, f.period_end,
             f.filed desc, f.accn desc
$$;

-- One row per (key, filing) where the value differs from the previous filing's value for the
-- same key: i.e. every restatement / revision, with what it changed from and to.
create or replace view fact_revisions as
with ordered as (
    select f.*,
           lag(f.value) over w as prev_value,
           lag(f.accn)  over w as prev_accn,
           lag(f.filed) over w as prev_filed
    from fact f
    window w as (partition by f.cik, f.taxonomy, f.tag, f.unit, f.period_start, f.period_end
                 order by f.filed, f.accn)
)
select cik, taxonomy, tag, unit, period_start, period_end,
       prev_accn, prev_filed, prev_value,
       accn, filed, value,
       value - prev_value                                   as abs_change,
       (value - prev_value) / nullif(abs(prev_value), 0)    as pct_change
from ordered
where prev_value is not null
  and value <> prev_value;

-- One row per key: how often it was reported, when first, and whether it ever changed.
create or replace view fact_first_seen as
select cik, taxonomy, tag, unit, period_start, period_end,
       min(filed)               as first_filed,
       max(filed)               as last_filed,
       count(*)                 as n_reports,
       count(distinct value)    as n_distinct_values
from fact
group by cik, taxonomy, tag, unit, period_start, period_end;
