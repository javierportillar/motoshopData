-- Forward-only reconciliation for environments that already applied
-- 20260712_001_app_users.sql before its credential-bearing seed was removed.
--
-- Delete only the untouched row created by that historical migration. Never
-- include or compare the old password hash: credentials do not belong in SQL.
delete from public.app_users
where username = 'admin'
  and email = 'admin@fragloesja.uk'
  and role = 'admin'
  and tenants_allowed = '["motoshop", "masvital"]'::jsonb
  and allowed_modules = '[]'::jsonb
  and active is true
  and created_by = 'migration'
  and updated_at = created_at;

-- Idempotent by construction: zero matching rows is a successful no-op.
