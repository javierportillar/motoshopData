# Supabase deployment guardrails

## Migration working directory

The repository keeps Supabase migrations under `infra/supabase/migrations`.
Always run the CLI from the repository root with `--workdir infra`; running it
from the repository root alone does not discover these migrations.

```bash
supabase --workdir infra link --project-ref <project-ref>
supabase --workdir infra migration list
supabase --workdir infra db push --dry-run
supabase --workdir infra db push
```

Do not use `migration repair` to mark migrations as applied until the remote
schema has been verified against every migration. The migration ledger is not
a substitute for applying or validating the SQL.

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
