BEGIN;

-- На всякий случай: если 02-grants.sql запускают отдельно
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tacacs_pg') THEN
    RAISE EXCEPTION 'Role tacacs_pg does not exist. Run 01-init.sql first.';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'tacacs') THEN
    RAISE EXCEPTION 'Schema tacacs does not exist. Run 01-init.sql first.';
  END IF;
END $$;

REVOKE ALL ON DATABASE tacacs_db FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE tacacs_db TO tacacs_pg;

REVOKE ALL ON SCHEMA tacacs FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA tacacs TO tacacs_pg;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA tacacs TO tacacs_pg;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA tacacs TO tacacs_pg;

GRANT EXECUTE
ON ALL FUNCTIONS IN SCHEMA tacacs TO tacacs_pg;

-- Default privileges на будущие объекты
ALTER DEFAULT PRIVILEGES FOR ROLE tacacs_pg IN SCHEMA tacacs
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tacacs_pg;

ALTER DEFAULT PRIVILEGES FOR ROLE tacacs_pg IN SCHEMA tacacs
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO tacacs_pg;

ALTER DEFAULT PRIVILEGES FOR ROLE tacacs_pg IN SCHEMA tacacs
  GRANT EXECUTE ON FUNCTIONS TO tacacs_pg;

COMMIT;
