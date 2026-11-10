from django.db import migrations, models


INSTALL_SQL = """
CREATE OR REPLACE FUNCTION audit_reject_auditlog_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'audit_auditlog is append-only' USING ERRCODE = '55000';
    RETURN NULL;
END;
$function$;

DROP TRIGGER IF EXISTS audit_auditlog_no_update_delete ON audit_auditlog;
CREATE TRIGGER audit_auditlog_no_update_delete
BEFORE UPDATE OR DELETE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_reject_auditlog_mutation();

DROP TRIGGER IF EXISTS audit_auditlog_no_truncate ON audit_auditlog;
CREATE TRIGGER audit_auditlog_no_truncate
BEFORE TRUNCATE ON audit_auditlog
FOR EACH STATEMENT EXECUTE FUNCTION audit_reject_auditlog_mutation();
"""

REMOVE_SQL = """
DROP TRIGGER IF EXISTS audit_auditlog_no_update_delete ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_auditlog_no_truncate ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_reject_auditlog_mutation();
"""


def install_audit_protection(apps, schema_editor):
    from django.conf import settings

    if settings.ENVIRONMENT in {"development", "production"}:
        schema_editor.execute(INSTALL_SQL)


def remove_audit_protection(apps, schema_editor):
    from django.conf import settings

    if settings.ENVIRONMENT in {"development", "production"}:
        schema_editor.execute(REMOVE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='target_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='target_type',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.RunPython(
            install_audit_protection,
            remove_audit_protection,
        ),
    ]
