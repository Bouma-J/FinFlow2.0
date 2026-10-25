import apps.credits.models
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('credits', '0009_creditapplication_mandatory_savings_rate_and_more'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='modifié le')),
                ('file', models.FileField(max_length=255, upload_to=apps.credits.models.credit_file_path, verbose_name='fichier scanné')),
                ('label', models.CharField(blank=True, max_length=150, verbose_name='libellé de la pièce')),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='credits.creditapplication', verbose_name='dossier')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_set', to='tenants.tenant', verbose_name='filiale')),
            ],
            options={
                'verbose_name': 'pièce du dossier',
                'verbose_name_plural': 'pièces du dossier',
                'ordering': ['created_at'],
            },
        ),
    ]
