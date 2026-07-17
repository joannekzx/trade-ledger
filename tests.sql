-- Data-quality checks. Every row should report 0 violations.
select 'unbalanced_entries' as check_name, count(*) as violations from (
    select entry_id from posting group by entry_id having sum(amount_signed) <> 0
) x
union all
-- the whole ledger nets to zero (follows from #1, but proves the invariant end-to-end)
select 'ledger_total_nonzero', case when coalesce(sum(amount_signed),0) = 0 then 0 else 1 end from posting
union all
-- idempotency: a source event was never loaded twice
select 'duplicate_event_ids', count(*) from (
    select external_event_id from journal_entry group by external_event_id having count(*) > 1
) y
union all
-- no orphan postings (entry + account both exist); the FKs guarantee this, we confirm it
select 'orphan_postings', count(*) from posting p
    left join journal_entry e on e.entry_id = p.entry_id
    left join accounts a on a.account_id = p.account_id
    where e.entry_id is null or a.account_id is null;
