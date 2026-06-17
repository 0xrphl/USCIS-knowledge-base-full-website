#!/bin/bash
set -e

echo "=== Restoring Supabase backup ==="
echo "This may take several minutes for large backups..."

# Run the backup SQL file, ignoring errors from missing Supabase-specific extensions
psql -U postgres -f /tmp/backup.sql 2>&1 || true

# Grant postgres membership in all created roles (fixes ownership issues)
psql -U postgres <<'EOSQL'
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT rolname FROM pg_roles WHERE rolname != 'postgres' AND rolname NOT LIKE 'pg_%'
    LOOP
        BEGIN
            EXECUTE format('GRANT %I TO postgres WITH ADMIN OPTION', r.rolname);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not grant role %: %', r.rolname, SQLERRM;
        END;
    END LOOP;
END
$$;
EOSQL

echo "=== Restore complete ==="
