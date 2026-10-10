-- Data-quality monitor. One row per check; `violations` is how many fact rows break it.
-- These are monitored, not enforced: real filings do trip some of them, and the point is to
-- see and explain them (see notebook 03), not to silently drop the rows.

select 'filed_before_period_end' as check_name,
       count(*)                  as violations,
       'filing date is earlier than the period it reports' as meaning
from fact
where filed < period_end

union all
select 'inverted_period', count(*), 'period_start is after period_end'
from fact
where period_start > period_end

union all
select 'implausible_duration', count(*), 'duration fact spanning more than 400 days'
from fact
where period_start is not null and period_end - period_start > 400

union all
select 'future_filed', count(*), 'filing date in the future'
from fact
where filed > current_date

union all
select 'instant_with_start', count(*), 'start date present on a balance-sheet style tag (Assets)'
from fact
where tag = 'Assets' and period_start is not null

order by check_name;
