"""Exhaustivité de l'analyse de référence avant soumission du dossier."""
from decimal import Decimal

from apps.workflow.services import WorkflowError


def _dec(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def assert_analysis_ready_for_submission(application):
    """
    Bloque la soumission si l'analyse de référence est incomplète.

    - Recommandation obligatoire
    - Sections minimales selon le type de client
    - Produit exigeant une garantie : au moins une garantie ACTIVE ou caution
    """
    from apps.guarantees.models import Guarantee
    from apps.sureties.models import SuretyEngagement

    from .models import FinancialAnalysis

    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    if reference is None:
        raise WorkflowError(
            "Une analyse financière de référence est obligatoire avant soumission."
        )

    from apps.configuration.services import analysis_requirement_failures

    failures = analysis_requirement_failures(application, reference)
    if failures:
        raise WorkflowError(" ".join(failures))

    if not reference.recommendation:
        raise WorkflowError(
            "L'analyse de référence doit porter une recommandation "
            "(favorable, sous conditions ou défavorable) avant soumission."
        )

    if (
        reference.recommendation
        == FinancialAnalysis.Recommendation.CONDITIONAL
        and not (reference.recommended_conditions or "").strip()
    ):
        raise WorkflowError(
            "Pour une recommandation sous conditions, précisez les conditions "
            "dans l'analyse de référence."
        )

    ctype = getattr(application.client, "client_type", "") or reference.client_type

    if ctype == "CORPORATE":
        if _dec(reference.turnover) <= 0:
            raise WorkflowError(
                "Analyse entreprise incomplète : le chiffre d'affaires est obligatoire."
            )
    elif ctype == "PROFESSIONAL":
        if not reference.members_count:
            raise WorkflowError(
                "Analyse groupement incomplète : indiquez le nombre de membres."
            )
        if _dec(reference.collective_contributions) <= 0 and _dec(
            reference.group_activity_turnover
        ) <= 0:
            raise WorkflowError(
                "Analyse groupement incomplète : renseignez les cotisations "
                "ou le CA de l'activité commune."
            )
    else:
        profile = getattr(reference, "individual_profile", "") or ""
        has_salary = (
            _dec(reference.salary_income) > 0 or _dec(reference.net_salary) > 0
            or _dec(reference.pension_income) > 0
        )
        has_activity_ca = _dec(reference.activity_turnover) > 0
        if not profile:
            if has_salary and (reference.has_side_activity or has_activity_ca):
                profile = FinancialAnalysis.IndividualProfile.MIXTE
            elif reference.has_side_activity or has_activity_ca:
                profile = FinancialAnalysis.IndividualProfile.INDEPENDANT
            else:
                profile = FinancialAnalysis.IndividualProfile.SALARIE

        if profile in (
            FinancialAnalysis.IndividualProfile.SALARIE,
            FinancialAnalysis.IndividualProfile.MIXTE,
        ):
            if not has_salary:
                raise WorkflowError(
                    "Analyse salarié incomplète : indiquez les revenus de salaire net ou de pension du demandeur."
                )
        if profile in (
            FinancialAnalysis.IndividualProfile.INDEPENDANT,
            FinancialAnalysis.IndividualProfile.MIXTE,
        ):
            if not has_activity_ca:
                raise WorkflowError(
                    "Analyse indépendant incomplète : indiquez le chiffre d'affaires "
                    "/ recettes de l'activité génératrice de revenus."
                )
        elif reference.has_side_activity and not has_activity_ca:
            raise WorkflowError(
                "Activité génératrice de revenus : indiquez le chiffre d'affaires "
                "/ recettes."
            )

        if reference.total_income <= 0:
            raise WorkflowError(
                "Analyse personne physique incomplète : les revenus du ménage "
                "(ou de l'activité) doivent être renseignés."
            )

    from .analysis_details import detail_metrics

    detailed = detail_metrics(reference)
    if detailed.get("debt_service_reconciled") is False:
        raise WorkflowError(
            "Rapprochez les mensualités des engagements détaillés avec le total consolidé avant soumission."
        )
    if detailed.get("forecast_deficit_months", 0) > 0 and not reference.recommended_conditions.strip():
        raise WorkflowError(
            "Le plan de trésorerie présente des mois déficitaires : précisez les mesures ou conditions proposées."
        )
    product = application.product
    if product and getattr(product, "requires_guarantee", False):
        has_g = application.guarantees.filter(
            status=Guarantee.Status.ACTIVE
        ).exists()
        has_s = SuretyEngagement.objects.filter(
            application=application,
            status=SuretyEngagement.Status.ACTIVE,
        ).exists()
        if not has_g and not has_s:
            raise WorkflowError(
                "Le produit exige une garantie ou une caution : "
                "rattachez-en au moins une avant soumission."
            )

    return reference


def refresh_reference_analysis(application):
    """Recalcule l'analyse de référence à partir des conditions actuelles."""
    if application is None or not getattr(application, "pk", None):
        return None
    reference = (
        application.financial_analyses.filter(is_reference=True).first()
        or application.financial_analyses.order_by("-created_at").first()
    )
    if reference is None:
        return None
    reference.save()
    return reference
