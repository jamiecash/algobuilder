# Generated by Django 3.2.5 on 2021-09-17 12:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feature', '0003_auto_20210917_1034'),
    ]

    operations = [
        migrations.AlterField(
            model_name='feature',
            name='calculation_frequency',
            field=models.CharField(max_length=255),
        ),
    ]
