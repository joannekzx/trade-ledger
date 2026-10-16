-- Balance of an account as-of a valid_time, as it was KNOWN at a given transaction_time.
-- The two filters are what make this bitemporal: move p_known and you see what you believed
-- then; move p_valid and you see the effective balance at that moment. A correction recorded
-- later changes balance_as_of(..., known = later) but never the earlier snapshot.
create or replace function balance_as_of(p_account text, p_valid timestamptz, p_known timestamptz)
returns numeric as $$
    select coalesce(sum(p.amount_signed), 0)
    from posting p
    join journal_entry e on e.entry_id = p.entry_id
    where p.account_id = p_account
      and e.valid_time  <= p_valid
      and e.recorded_at <= p_known;
$$ language sql stable;

-- current balance = as-of now, known now
create or replace view current_balances as
    select a.account_id, a.type, balance_as_of(a.account_id, now(), now()) as balance
    from accounts a
    order by a.account_id;

-- statement / replay: the ordered postings that build up an account's balance
create or replace view account_statement as
    select p.account_id, e.valid_time, e.recorded_at, e.external_event_id,
           e.reverses_event_id, p.amount_signed, e.description
    from posting p
    join journal_entry e on e.entry_id = p.entry_id
    order by p.account_id, e.valid_time, e.recorded_at;
