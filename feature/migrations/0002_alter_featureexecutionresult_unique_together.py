# Generated by Django 3.2.5 on 2021-09-13 08:13

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('feature', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='featureexecutionresult',
            unique_together={('feature_execution', 'time')},
        ),
    ]
