# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0006_add_email_tel_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitytemplate',
            name='notes',
            field=models.TextField(blank=True, help_text='Instructions or notes for users filling out this template'),
        ),
    ]
