from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scans', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scanimage',
            name='order',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Capture sequence order (0=front 0 degrees, 1-7=clockwise 360 degrees)',
            ),
        ),
        migrations.AlterModelOptions(
            name='scanimage',
            options={'ordering': ['order']},
        ),
    ]
