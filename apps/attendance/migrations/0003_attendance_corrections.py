import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_attendance_core'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceCorrection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('corrected_field', models.CharField(choices=[('CHECK_IN_AT', 'Check-in time'), ('CHECK_OUT_AT', 'Check-out time')], max_length=16)),
                ('previous_value', models.DateTimeField(blank=True, null=True)),
                ('new_value', models.DateTimeField()),
                ('reason', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('corrected_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attendance_corrections', to=settings.AUTH_USER_MODEL)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='corrections', to='attendance.attendancesession')),
            ],
            options={
                'ordering': ['created_at', 'pk'],
                'constraints': [models.CheckConstraint(condition=models.Q(('corrected_field__in', ['CHECK_IN_AT', 'CHECK_OUT_AT'])), name='attendance_correction_field_valid'), models.CheckConstraint(condition=models.Q(('corrected_field', 'CHECK_OUT_AT'), ('previous_value__isnull', False), _connector='OR'), name='attendance_correction_previous_valid'), models.CheckConstraint(condition=models.Q(('reason', ''), _negated=True), name='attendance_correction_reason_required')],
            },
        ),
    ]
