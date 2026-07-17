-- Trade ledger schema. Two invariants are enforced by the DATABASE, not hoped for by the app:
--   1. double-entry: every journal entry's postings net to zero.
--   2. append-only: journal entries and postings are never updated or deleted -- corrections
--      are made by posting a reversing entry.
-- Balances are never stored; they're derived by summing postings (see queries.sql).

create table accounts (
    account_id  text primary key,
    type        text not null check (type in ('asset','liability','equity','revenue','expense')),
    currency    text not null default 'USD',
    opened_at   timestamptz not null default now()
);

create table journal_entry (
    entry_id           bigserial primary key,
    external_event_id  text unique not null,   -- idempotency key from the source; replays collapse here
    description        text,
    valid_time         timestamptz not null,   -- when the movement is effective
    recorded_at        timestamptz not null,   -- when we wrote it down (transaction time)
    reverses_event_id  text                    -- external id of the entry this reverses, if any
);

create table posting (
    posting_id     bigserial primary key,
    entry_id       bigint not null references journal_entry(entry_id),
    account_id     text   not null references accounts(account_id),
    amount_signed  numeric(18,2) not null      -- +debit / -credit; per entry these sum to 0
);

create index on posting (account_id);
create index on journal_entry (valid_time);
create index on journal_entry (recorded_at);

-- ---- invariant 1: double-entry ----------------------------------------------------------
-- deferred to commit so an entry's legs can be inserted one row at a time inside a txn.
create or replace function assert_entry_balanced() returns trigger as $$
declare
    bad bigint;
begin
    select entry_id into bad
    from posting
    where entry_id = coalesce(new.entry_id, old.entry_id)
    group by entry_id
    having sum(amount_signed) <> 0;

    if found then
        raise exception 'unbalanced journal entry %: postings must sum to zero', bad;
    end if;
    return null;
end;
$$ language plpgsql;

create constraint trigger posting_balanced
    after insert or update or delete on posting
    deferrable initially deferred
    for each row execute function assert_entry_balanced();

-- ---- invariant 2: append-only -----------------------------------------------------------
-- once written, a row can't change; fixing a mistake means posting a reversing entry.
create or replace function block_mutation() returns trigger as $$
begin
    raise exception 'ledger is append-only: % on % not allowed (post a reversing entry instead)',
        tg_op, tg_table_name;
end;
$$ language plpgsql;

create trigger no_change_journal before update or delete on journal_entry
    for each row execute function block_mutation();
create trigger no_change_posting before update or delete on posting
    for each row execute function block_mutation();

-- fixed chart of accounts; small on purpose
insert into accounts (account_id, type) values
    ('cash','asset'), ('settlement','asset'), ('equity_position','asset'),
    ('counterparty_payable','liability'), ('fees_expense','expense'), ('revenue','revenue');
