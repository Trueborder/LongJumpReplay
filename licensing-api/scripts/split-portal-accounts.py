"""Prepare a reviewed, guarded split from private D1 SQL exports; never contacts a server."""
import argparse
import json
import sqlite3
from pathlib import Path

PROTECTED_EMAIL = 'xpisar10@gmail.com'
COPY_TABLES = ('customers', 'customer_password_credentials', 'portal_profiles', 'privacy_requests')


def load(path):
    connection = sqlite3.connect(':memory:')
    connection.executescript(Path(path).read_text(encoding='utf-8'))
    return connection


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def plan(ljr, minecraft):
    # Include linked accounts, unfinished pairing, orders, consents and game history.
    ids = set()
    for (table,) in minecraft.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if table in COPY_TABLES or table in ('portal_sessions', 'portal_login_codes', 'password_reset_codes', 'portal_registration_challenges'):
            continue
        columns = [row[1] for row in minecraft.execute(f'PRAGMA table_info("{table}")')]
        if 'customer_id' in columns:
            ids.update(row[0] for row in minecraft.execute(f'SELECT DISTINCT customer_id FROM "{table}" WHERE customer_id IS NOT NULL'))
    # Completed legacy Minecraft registration also exists before player pairing:
    # it has a password and no required LJR profile/licence/order.
    ids.update(row[0] for row in ljr.execute('''SELECT c.id FROM customers c
        JOIN customer_password_credentials password ON password.customer_id=c.id
        WHERE NOT EXISTS(SELECT 1 FROM portal_profiles profile WHERE profile.customer_id=c.id)
        AND NOT EXISTS(SELECT 1 FROM licenses licence WHERE licence.customer_id=c.id)
        AND NOT EXISTS(SELECT 1 FROM ljr_orders orders WHERE orders.customer_id=c.id)'''))
    customers = [row for row in ljr.execute('SELECT * FROM customers') if row[0] in ids]
    if set(row[0] for row in customers) != ids:
        raise ValueError('A Minecraft identity has no matching source customer; inspect before proceeding')
    targets = [row for row in customers if row[1].lower() != PROTECTED_EMAIL]
    target_ids = ','.join(literal(row[0]) for row in targets) or "''"
    target_emails = ','.join(literal(row[1]) for row in targets) or "''"
    copy = []
    for table in COPY_TABLES:
        columns = [row[1] for row in ljr.execute(f'PRAGMA table_info("{table}")')]
        key = 'id' if table == 'customers' else 'customer_id'
        for customer in customers:
            for row in ljr.execute(f'SELECT * FROM "{table}" WHERE {key}=?', (customer[0],)):
                copy.append(f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({",".join(map(literal, row))});')
    # No sessions/OTP/reset/setup challenges cross the account boundary.
    # Migration changes neither password hashes nor customer timestamps.
    guards = [f'(SELECT count(*) FROM customers WHERE id IN ({target_ids}) AND lower(email)!={literal(PROTECTED_EMAIL)})={len(targets)}',
              f'NOT EXISTS(SELECT 1 FROM licenses WHERE customer_id IN ({target_ids}))',
              f'NOT EXISTS(SELECT 1 FROM ljr_orders WHERE customer_id IN ({target_ids}))']
    for row in targets:
        guards.append(f'EXISTS(SELECT 1 FROM customers WHERE id={literal(row[0])} AND email={literal(row[1])} AND updated_at={literal(row[4])})')
        credential = ljr.execute('SELECT password_hash,updated_at FROM customer_password_credentials WHERE customer_id=?', (row[0],)).fetchone()
        if credential:
            guards.append(f'EXISTS(SELECT 1 FROM customer_password_credentials WHERE customer_id={literal(row[0])} AND password_hash={literal(credential[0])} AND updated_at={credential[1]})')
    delete = ['CREATE TABLE portal_split_guard (ok INTEGER NOT NULL CHECK(ok=1));',
              'INSERT INTO portal_split_guard(ok) SELECT CASE WHEN ' + ' AND '.join(guards) + ' THEN 1 ELSE 0 END;']
    for (table,) in ljr.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='customers'"):
        columns = [row[1] for row in ljr.execute(f'PRAGMA table_info("{table}")')]
        conditions = []
        if 'customer_id' in columns:
            conditions.append(f'customer_id IN ({target_ids})')
        if 'email' in columns and table in ('portal_login_codes', 'password_reset_codes', 'portal_registration_challenges', 'verification_codes'):
            conditions.append(f'email IN ({target_emails})')
        if conditions:
            delete.append(f'DELETE FROM "{table}" WHERE ({" OR ".join(conditions)}) AND NOT EXISTS(SELECT 1 FROM customers protected WHERE protected.id="{table}".customer_id AND lower(protected.email)={literal(PROTECTED_EMAIL)});' if 'customer_id' in columns else f'DELETE FROM "{table}" WHERE {" OR ".join(conditions)};')
    delete.extend([f'DELETE FROM customers WHERE id IN ({target_ids}) AND lower(email)!={literal(PROTECTED_EMAIL)};', 'DROP TABLE portal_split_guard;'])
    return '\n'.join(copy) + '\n', '\n'.join(delete) + '\n', {'minecraft_accounts': len(customers), 'ljr_accounts_to_remove': len(targets), 'protected_original_untouched': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ljr', required=True)
    parser.add_argument('--minecraft', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    ljr, minecraft = load(args.ljr), load(args.minecraft)
    copy, delete, summary = plan(ljr, minecraft)
    # Rehearse on local copies, with foreign keys and protected-row comparison.
    before = list(ljr.execute('SELECT * FROM customers WHERE lower(email)=?', (PROTECTED_EMAIL,)))
    if not minecraft.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='customers'").fetchone():
        minecraft.executescript(Path('economysuite-migrations/0004_separate_accounts.sql').read_text(encoding='utf-8'))
    minecraft.executescript(copy)
    ljr.execute('PRAGMA foreign_keys=ON')
    ljr.executescript('BEGIN;\n' + delete + '\nCOMMIT;')
    assert before == list(ljr.execute('SELECT * FROM customers WHERE lower(email)=?', (PROTECTED_EMAIL,)))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'copy-minecraft.sql').write_text(copy, encoding='utf-8')
    (output / 'remove-ljr.sql').write_text(delete, encoding='utf-8')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
