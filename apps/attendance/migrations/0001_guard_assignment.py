import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        BtreeGistExtension(),
        migrations.CreateModel(
            name='GuardAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='guard_assignments', to=settings.AUTH_USER_MODEL)),
                ('guard', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='employee_assignments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['guard', 'ended_at', 'employee'], name='attendance_guard_scope_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('employee', models.F('guard')), _negated=True), name='attendance_assignment_not_self'), models.CheckConstraint(condition=models.Q(('ended_at__isnull', True), ('ended_at__gt', models.F('started_at')), _connector='OR'), name='attendance_assignment_dates_valid'), models.UniqueConstraint(condition=models.Q(('ended_at__isnull', True)), fields=('employee',), name='attendance_one_open_assignment'), django.contrib.postgres.constraints.ExclusionConstraint(expressions=[('employee', '='), (models.Func('started_at', 'ended_at', django.contrib.postgres.fields.ranges.RangeBoundary(), function='TSTZRANGE', output_field=django.contrib.postgres.fields.ranges.DateTimeRangeField()), '&&')], name='attendance_assignment_no_overlap')],
            },
        ),
    ]
