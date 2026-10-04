from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0002_add_order_field_to_scanimage'),
    ]

    operations = [
        migrations.CreateModel(
            name='KeenToolsQuota',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_scans', models.PositiveIntegerField(default=40, help_text='Maximum allowed KeenTools scans')),
                ('used_scans', models.PositiveIntegerField(default=0, help_text='Number of scans processed by KeenTools since last reset')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'KeenTools Quota',
                'verbose_name_plural': 'KeenTools Quota',
            },
        ),
        migrations.AlterField(
            model_name='scan',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING_APPROVAL', 'Pending Approval'),
                    ('PROCESSING', 'Processing'),
                    ('COMPLETED', 'Completed'),
                    ('FAILED', 'Failed'),
                ],
                default='PROCESSING',
                max_length=20,
            ),
        ),
    ]
