from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_attendance_corrections'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='attendancerequest',
            name='attendance_request_status_valid',
        ),
        migrations.RemoveConstraint(
            model_name='attendancerequest',
            name='attendance_request_review_state_valid',
        ),
        migrations.RemoveConstraint(
            model_name='attendancerequest',
            name='attendance_request_session_link_valid',
        ),
        migrations.AlterField(
            model_name='attendancerequest',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=16),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'])), name='attendance_request_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('auto_approved', False), ('rejection_reason', ''), ('reviewed_at__isnull', True), ('reviewed_by__isnull', True), ('status', 'PENDING')), models.Q(('rejection_reason', ''), ('reviewed_at__isnull', False), ('status', 'APPROVED'), models.Q(models.Q(('auto_approved', True), ('reviewed_by__isnull', True)), models.Q(('auto_approved', False), ('reviewed_by__isnull', False)), _connector='OR')), models.Q(('auto_approved', False), ('reviewed_at__isnull', False), ('reviewed_by__isnull', False), ('status', 'REJECTED'), models.Q(('rejection_reason', ''), _negated=True)), models.Q(('auto_approved', False), ('rejection_reason', ''), ('reviewed_at__isnull', True), ('reviewed_by__isnull', True), ('status', 'CANCELLED')), _connector='OR'), name='attendance_request_review_state_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('request_type', 'CHECK_OUT'), ('session__isnull', False)), models.Q(('request_type', 'CHECK_IN'), ('session__isnull', False), ('status', 'APPROVED')), models.Q(('request_type', 'CHECK_IN'), ('session__isnull', True), ('status__in', ['PENDING', 'REJECTED', 'CANCELLED'])), _connector='OR'), name='attendance_request_session_link_valid'),
        ),
    ]
