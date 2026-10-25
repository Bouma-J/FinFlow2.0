"""Utilitaires transverses liés aux comptes utilisateurs."""

# Taille des colonnes qui stockent ce libellé (FinancialAnalysis.author_role,
# FieldVisit.visitor_role). Le dépassement provoquerait une erreur SGBD.
ROLE_LABEL_MAX_LENGTH = 150


def user_role_label(user, max_length=ROLE_LABEL_MAX_LENGTH):
    """Libellé lisible du profil/rôle d'un utilisateur.

    Utilisé pour figer (snapshot) le profil de l'auteur d'une analyse ou d'une
    visite terrain, afin que la traçabilité reste fiable même si les rôles de
    l'utilisateur évoluent par la suite.

    Les groupes Django d'une filiale portent un nom technique généré
    (`__ff_<filiale>__<hash>`, ~55 caractères) : on résout le libellé métier
    via `TenantRole`, et on borne le résultat à la taille de la colonne cible.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return ""

    names = sorted(
        _role_name(group)
        for group in user.groups.select_related("tenant_role").all()
    )
    if names:
        return _join_within(names, max_length)
    if user.is_superuser:
        return "Administrateur"
    if getattr(user, "is_group_level", False):
        return "Responsable Groupe"
    return ""


def _role_name(group):
    """Libellé métier du rôle, ou nom du groupe s'il n'est pas rattaché."""
    from apps.accounts.services import (
        CREDIT_COMMITTEE_GROUP_ROLE_NAME,
        GROUP_CREDIT_COMMITTEE_DJANGO_GROUP,
    )

    if group.name == GROUP_CREDIT_COMMITTEE_DJANGO_GROUP:
        return CREDIT_COMMITTEE_GROUP_ROLE_NAME
    role = getattr(group, "tenant_role", None)
    return role.name if role is not None else group.name


def _join_within(names, max_length):
    """Concatène les rôles sans dépasser `max_length` (suffixe « (+N) » sinon)."""
    joined = ", ".join(names)
    if max_length is None or len(joined) <= max_length:
        return joined

    kept = []
    for name in names:
        candidate = kept + [name]
        omitted = len(names) - len(candidate)
        text = ", ".join(candidate) + (f" (+{omitted})" if omitted else "")
        if len(text) > max_length:
            break
        kept = candidate

    if not kept:
        # Un seul rôle dépasse déjà à lui seul : troncature franche.
        return names[0][:max_length]
    omitted = len(names) - len(kept)
    return ", ".join(kept) + (f" (+{omitted})" if omitted else "")
