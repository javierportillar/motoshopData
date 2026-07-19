# Supabase deployment guardrails

## `app_users` credential reconciliation

Deployment is **blocked** until an operator rotates the historical legacy admin
password outside this repository. The new password or hash must only travel
through an approved secret channel; do not paste it into a migration, commit,
issue, log, or deployment note.

Before releasing the users-and-permissions changes:

1. Rotate the legacy admin credential in the external secret/configuration
   source used by the deployed API.
2. Apply the Supabase migrations through the normal deployment pipeline,
   including `20260719_001_reconcile_app_users_seed.sql`.
3. Create or explicitly migrate an admin through `POST /api/admin/users` with a
   newly generated password and `migrate_legacy=true` when the username still
   exists in `users.yaml`.
4. Verify the managed admin can log in and that at least one active admin remains
   before removing any legacy identity.

The reconciliation migration removes only the untouched historical seed row and
contains no credential. It is safe to run repeatedly.
