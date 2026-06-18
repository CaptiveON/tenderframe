-- Least-privilege application DB role (SECURITY_AUDIT F7).
--
-- The app must NOT connect as the postgres superuser in any shared/public
-- deploy. Run this ONCE as an admin against the target database, then point
-- the app's DATABASE_URL at this role. Replace the password with a strong
-- value from your platform's secret store (never commit the real password).
--
--   psql "$ADMIN_DATABASE_URL" -f least_privilege_role.sql
--   DATABASE_URL=postgresql://tenderframe_app:<secret>@host:5432/<db>
--
-- Run AFTER `alembic upgrade head` (tables + the append-only trigger must
-- exist first).

-- 1. Role
CREATE ROLE tenderframe_app LOGIN PASSWORD 'CHANGE_ME_USE_SECRET_STORE';

-- 2. Connect + schema usage
GRANT CONNECT ON DATABASE current_database() TO tenderframe_app;  -- edit db name if needed
GRANT USAGE ON SCHEMA public TO tenderframe_app;

-- 3. App tables: full CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON
    users, chat_sessions, messages,
    catalog, documents, chunks, facts
TO tenderframe_app;

-- 4. audit_log: INSERT + SELECT only — NO update/delete grant.
--    (Defence in depth alongside the append-only trigger from migration 0002.)
GRANT SELECT, INSERT ON audit_log TO tenderframe_app;

-- 5. Sequences (bigserial / id generation)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tenderframe_app;

-- 6. Do NOT grant: CREATE, DDL, or any superuser attribute.
--    Migrations run separately as an admin/owner role, not as tenderframe_app.
