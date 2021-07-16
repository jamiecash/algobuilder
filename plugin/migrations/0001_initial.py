# Generated by Django 3.2.5 on 2021-07-15 08:50

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Plugin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_name', models.FileField(max_length=200, upload_to='plugin\\plugins')),
                ('requirements_file', models.FileField(max_length=200, upload_to='plugin\\requirements')),
            ],
        ),
    ]
