-- Phase 1: non-superuser application role for Row Level Security.
-- Development password only; production deployments must rotate it.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orgweave_app') THEN
    CREATE ROLE orgweave_app LOGIN
      PASSWORD 'orgweave_app_dev_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE orgweave TO orgweave_app;
GRANT USAGE ON SCHEMA public TO orgweave_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO orgweave_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO orgweave_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO orgweave_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO orgweave_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO orgweave_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO orgweave_app;
