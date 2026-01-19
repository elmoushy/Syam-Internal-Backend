# Generated migration to add email and tel data types

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0005_add_active_and_submitted'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activitycolumndefinition',
            name='data_type',
            field=models.CharField(
                choices=[
                    ('text', 'Text'),
                    ('number', 'Number'),
                    ('date', 'Date'),
                    ('email', 'Email'),
                    ('tel', 'Phone'),
                    ('boolean', 'Yes/No'),
                    ('select', 'Dropdown')
                ],
                default='text',
                max_length=20
            ),
        ),
    ]
