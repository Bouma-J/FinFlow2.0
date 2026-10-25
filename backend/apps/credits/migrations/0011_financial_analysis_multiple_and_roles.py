import django.db.models.deletion
from django.db import migrations, models


ROLE_LABEL_MAX_LENGTH = 150


def populate_author_roles(apps, schema_editor):
    """Fige le profil des auteurs pour les analyses/visites existantes."""
    FinancialAnalysis = apps.get_model("credits", "FinancialAnalysis")
    FieldVisit = apps.get_model("credits", "FieldVisit")

    # Les groupes d'une filiale portent un nom technique généré d'environ 55
    # caractères : on résout le libellé métier via TenantRole et on borne le
    # résultat, sinon la migration échoue (varchar(150)) sur le premier
    # utilisateur portant 3 rôles ou plus.
    try:
        TenantRole = apps.get_model("accounts", "TenantRole")
        role_names = dict(TenantRole.objects.values_list("group_id", "name"))
    except LookupError:
        role_names = {}

    def role_label(user):
        if user is None:
            return ""
        names = sorted(
            role_names.get(group_id) or group_name
            for group_id, group_name in user.groups.values_list("id", "name")
        )
        if names:
            kept = []
            for name in names:
                candidate = kept + [name]
                if len(", ".join(candidate)) > ROLE_LABEL_MAX_LENGTH:
                    break
                kept = candidate
            if not kept:
                return names[0][:ROLE_LABEL_MAX_LENGTH]
            return ", ".join(kept)
        if getattr(user, "is_superuser", False):
            return "Administrateur"
        if getattr(user, "is_group_level", False):
            return "Responsable Groupe"
        return ""

    for analysis in FinancialAnalysis.objects.select_related("created_by").all():
        label = role_label(analysis.created_by)
        if label and not analysis.author_role:
            analysis.author_role = label
            analysis.save(update_fields=["author_role"])

    for visit in FieldVisit.objects.select_related("visited_by").all():
        label = role_label(visit.visited_by)
        if label and not visit.visitor_role:
            visit.visitor_role = label
            visit.save(update_fields=["visitor_role"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0010_creditdocument"),
    ]

    operations = [
        migrations.AlterField(
            model_name="financialanalysis",
            name="application",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="financial_analyses",
                to="credits.creditapplication",
                verbose_name="dossier",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="author_role",
            field=models.CharField(
                blank=True,
                help_text="Rôle/profil de l'auteur figé au moment de l'analyse.",
                max_length=150,
                verbose_name="profil de l'auteur",
            ),
        ),
        migrations.AlterModelOptions(
            name="financialanalysis",
            options={
                "ordering": ["created_at"],
                "verbose_name": "analyse financière",
                "verbose_name_plural": "analyses financières",
            },
        ),
        migrations.AddField(
            model_name="fieldvisit",
            name="visitor_role",
            field=models.CharField(
                blank=True,
                help_text="Rôle/profil de l'auteur figé au moment de la visite.",
                max_length=150,
                verbose_name="profil de l'auteur",
            ),
        ),
        migrations.RunPython(populate_author_roles, noop),
    ]
