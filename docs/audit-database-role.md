# Restricted production database role

Audit triggers prevent `UPDATE`, `DELETE`, and `TRUNCATE` on `audit_auditlog` in
development and production. PostgreSQL table owners and superusers can disable
triggers, so the production application must not connect as either.

Use a separate migration owner to run Django migrations. After migrations, create a
runtime role using credentials from the deployment secret store. Replace the example
role name and password before executing these commands as the database owner:

```sql
CREATE ROLE attendance_app LOGIN PASSWORD '<runtime-password>';
GRANT CONNECT ON DATABASE attendance TO attendance_app;
GRANT USAGE ON SCHEMA public TO attendance_app;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public TO attendance_app;
GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA public TO attendance_app;

REVOKE UPDATE, DELETE, TRUNCATE
ON TABLE audit_auditlog FROM attendance_app;
GRANT SELECT, INSERT
ON TABLE audit_auditlog TO attendance_app;

ALTER DEFAULT PRIVILEGES FOR ROLE attendance_migrator IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO attendance_app;
ALTER DEFAULT PRIVILEGES FOR ROLE attendance_migrator IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO attendance_app;
```

Run migrations with the non-runtime owner, then start Django with
`POSTGRES_USER=attendance_app`. Ensure the runtime role does not own
`audit_auditlog`:

```sql
SELECT tableowner
FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'audit_auditlog';
```

The returned owner must be the migration owner, not `attendance_app`. Direct access
by the migration owner or a database superuser remains outside the application-level
immutability guarantee.
