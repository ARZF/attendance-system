import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0001_guard_assignment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('check_in_at', models.DateTimeField()),
                ('check_out_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attendance_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-check_in_at', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_type', models.CharField(choices=[('CHECK_IN', 'Check in'), ('CHECK_OUT', 'Check out')], max_length=16)),
                ('attendance_at', models.DateTimeField()),
                ('requested_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING', max_length=16)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True, default='')),
                ('auto_approved', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attendance_requests', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_attendance_requests', to=settings.AUTH_USER_MODEL)),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='requests', to='attendance.attendancesession')),
            ],
            options={
                'ordering': ['requested_at', 'pk'],
            },
        ),
        migrations.AddIndex(
            model_name='attendancesession',
            index=models.Index(fields=['employee', '-check_in_at'], name='att_session_emp_checkin_idx'),
        ),
        migrations.AddConstraint(
            model_name='attendancesession',
            constraint=models.UniqueConstraint(condition=models.Q(('check_out_at__isnull', True)), fields=('employee',), name='attendance_one_active_session'),
        ),
        migrations.AddConstraint(
            model_name='attendancesession',
            constraint=models.CheckConstraint(condition=models.Q(('check_out_at__isnull', True), ('check_out_at__gt', models.F('check_in_at')), _connector='OR'), name='attendance_session_dates_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancesession',
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(expressions=[('employee', '='), (models.Func('check_in_at', 'check_out_at', django.contrib.postgres.fields.ranges.RangeBoundary(), function='TSTZRANGE', output_field=django.contrib.postgres.fields.ranges.DateTimeRangeField()), '&&')], name='attendance_session_no_overlap'),
        ),
        migrations.AddIndex(
            model_name='attendancerequest',
            index=models.Index(fields=['status', 'request_type', 'requested_at'], name='att_request_queue_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancerequest',
            index=models.Index(fields=['employee', 'status', 'requested_at'], name='att_request_employee_idx'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(('request_type__in', ['CHECK_IN', 'CHECK_OUT'])), name='attendance_request_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['PENDING', 'APPROVED', 'REJECTED'])), name='attendance_request_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'PENDING')), fields=('employee', 'request_type'), name='attendance_one_pending_request_type'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('auto_approved', False), ('rejection_reason', ''), ('reviewed_at__isnull', True), ('reviewed_by__isnull', True), ('status', 'PENDING')), models.Q(('rejection_reason', ''), ('reviewed_at__isnull', False), ('status', 'APPROVED'), models.Q(models.Q(('auto_approved', True), ('reviewed_by__isnull', True)), models.Q(('auto_approved', False), ('reviewed_by__isnull', False)), _connector='OR')), models.Q(('auto_approved', False), ('reviewed_at__isnull', False), ('reviewed_by__isnull', False), ('status', 'REJECTED'), models.Q(('rejection_reason', ''), _negated=True)), _connector='OR'), name='attendance_request_review_state_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('request_type', 'CHECK_OUT'), ('session__isnull', False)), models.Q(('request_type', 'CHECK_IN'), ('session__isnull', False), ('status', 'APPROVED')), models.Q(('request_type', 'CHECK_IN'), ('session__isnull', True), ('status__in', ['PENDING', 'REJECTED'])), _connector='OR'), name='attendance_request_session_link_valid'),
        ),
        migrations.AddConstraint(
            model_name='attendancerequest',
            constraint=models.CheckConstraint(condition=models.Q(('reviewed_by__isnull', True), models.Q(('reviewed_by', models.F('employee')), _negated=True), _connector='OR'), name='attendance_request_not_self_reviewed'),
        ),
    ]
