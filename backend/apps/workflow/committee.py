"""Présences et votes nominatifs, avec quorum et conflits d'intérêts."""

from .services import WorkflowError
from django.core.exceptions import ValidationError


def validate_committee(task, user, record, *, approve=True, reject=False):
    # Le quorum historique à une personne reste utilisable sans saisie nouvelle.
    if (
        not record
        and task.step.committee_quorum <= 1
        and not task.step.committee_record_required
    ):
        record = {
            "participants": [
                {
                    "user": str(user.pk),
                    "vote": "FOR" if approve else "AGAINST" if reject else "ABSTAIN",
                    "conflict": False,
                }
            ]
        }
    if not isinstance(record, dict) or not isinstance(record.get("participants"), list):
        raise WorkflowError("Renseignez les participants et les votes du comité.")
    from apps.accounts.models import User
    from .services import _get_credit_application, user_can_act

    participants = record["participants"]
    if len(participants) > 100:
        raise WorkflowError("Le comité est limité à 100 participants.")
    seen, eligible, favorable, unfavorable = set(), 0, 0, 0
    cleaned = []
    for row in participants:
        if not isinstance(row, dict):
            raise WorkflowError("Participant invalide.")
        identifier = str(row.get("user") or "")
        try:
            member = User.objects.get(pk=identifier, is_active=True)
        except (User.DoesNotExist, ValueError, ValidationError):
            raise WorkflowError("Participant introuvable.")
        identifier = str(member.pk)
        if identifier in seen:
            raise WorkflowError("Un participant ne peut voter deux fois.")
        seen.add(identifier)
        if member.tenant_id != task.tenant_id and not member.is_group_level:
            raise WorkflowError("Le participant appartient à une autre filiale.")
        if not user_can_act(
            member,
            task.step,
            application=_get_credit_application(task.instance),
            amount=task.instance.amount,
        ):
            raise WorkflowError("Un participant n'est pas habilité pour ce comité.")
        vote = row.get("vote")
        conflict = row.get("conflict", False)
        if not isinstance(conflict, bool) or vote not in ("FOR", "AGAINST", "ABSTAIN"):
            raise WorkflowError("Vote ou déclaration de conflit invalide.")
        if conflict and vote != "ABSTAIN":
            raise WorkflowError("Un participant en conflit doit s'abstenir.")
        target = task.instance.target
        if member.pk in {
            getattr(target, "created_by_id", None),
            getattr(target, "submitted_by_id", None),
        }:
            if vote != "ABSTAIN":
                raise WorkflowError(
                    "L'initiateur doit s'abstenir sur son propre dossier."
                )
            conflict = True
        if not conflict:
            eligible += 1
            favorable += vote == "FOR"
            unfavorable += vote == "AGAINST"
        cleaned.append(
            {
                "user": identifier,
                "name": str(member),
                "vote": vote,
                "conflict": conflict,
            }
        )
    if eligible < task.step.committee_quorum:
        raise WorkflowError("Le quorum hors conflits d'intérêts n'est pas atteint.")
    denominator = (
        favorable + unfavorable
        if task.step.committee_abstentions == "EXCLUDE"
        else eligible
    )

    def majority_met(votes):
        if denominator <= 0:
            return False
        if task.step.committee_majority == "UNANIMOUS":
            return votes == denominator
        if task.step.committee_majority == "QUALIFIED":
            return (
                votes * task.step.committee_majority_denominator
                >= denominator * task.step.committee_majority_numerator
            )
        return votes * 2 > denominator

    if approve and not majority_met(favorable):
        raise WorkflowError("La majorité favorable du comité n'est pas atteinte.")
    if reject and not majority_met(unfavorable):
        raise WorkflowError("La majorité défavorable du comité n'est pas atteinte.")
    return {
        "participants": cleaned,
        "recorded_by": str(user.pk),
        "rules": {
            "quorum": task.step.committee_quorum,
            "majority": task.step.committee_majority,
            "numerator": task.step.committee_majority_numerator,
            "denominator": task.step.committee_majority_denominator,
            "abstentions": task.step.committee_abstentions,
            "record_required": task.step.committee_record_required,
            "pv_required": task.step.committee_pv_required,
        },
        "counts": {
            "eligible": eligible,
            "for": favorable,
            "against": unfavorable,
            "abstentions": eligible - favorable - unfavorable,
            "majority_base": denominator,
        },
    }
