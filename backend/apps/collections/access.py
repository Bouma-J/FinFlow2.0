"""Droits métier du recouvrement (tranche, dossier, auteur)."""
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.accounts.capabilities import (
    AGENCY_MANAGER, COLLECTION_BROAD_VIEW, COLLECTION_MANAGER,
    COLLECTION_OFFICER, LEGAL_OFFICER, RELATIONSHIP_MANAGER, TENANT_ADMIN,
    user_capabilities, users_with_capability,
)
from apps.common.access import DataScope, get_user_agency_ids

from .models import CollectionCase, CollectionTranche

_DENY_OPERATE = (
    "Vous ne pouvez pas modifier ce dossier à cette tranche. "
    "Utilisez le dialogue pour une question, une demande ou une recommandation."
)
_DENY_EDIT_OWN = "Vous ne pouvez modifier que les éléments que vous avez créés."
_DENY_ADMIN = "Réservé aux administrateurs filiale et groupe."

_COLLECTION_ROLES = frozenset({COLLECTION_OFFICER})
_LEGAL_ROLES = frozenset({LEGAL_OFFICER})
_BROAD_VIEW_ROLES = frozenset({COLLECTION_BROAD_VIEW})


def uses_special_collection_scope(user) -> bool:
    """True si le périmètre recouvrement remplace data_scope OWN/AGENCY."""
    if is_finflow_admin(user):
        return True
    names = user_capabilities(user)
    return bool(
        names
        & (
            _BROAD_VIEW_ROLES
            | {RELATIONSHIP_MANAGER, AGENCY_MANAGER}
        )
    )


def user_role_names(user) -> set[str]:
    cached = getattr(user, "_ff_role_names", None)
    if cached is not None:
        return cached
    names: set[str] = set()
    if user and getattr(user, "is_authenticated", False):
        for group in user.groups.select_related("tenant_role").all():
            role = getattr(group, "tenant_role", None)
            names.add(role.name if role is not None else group.name)
    if user is not None:
        user._ff_role_names = names
    return names


def user_display_name(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.username


def is_finflow_admin(user) -> bool:
    """Administrateur filiale, administrateur groupe, ou superutilisateur."""
    if not user or not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if getattr(user, "is_group_level", False) and user.is_staff:
        return True
    return TENANT_ADMIN in user_capabilities(user)


def is_collection_officer(user) -> bool:
    return bool(user_capabilities(user) & _COLLECTION_ROLES)


def require_finflow_admin(user) -> None:
    if not is_finflow_admin(user):
        raise PermissionDenied(_DENY_ADMIN)


def officers_own_cases_q(user) -> Q:
    """Dossiers instruits / soumis par le chargé d'affaires."""
    from apps.credits.models import CreditApplication

    own = Q(loan__application__submitted_by=user)
    if any(f.name == "created_by" for f in CreditApplication._meta.fields):
        own |= Q(loan__application__created_by=user)
    return own


def mine_collection_cases(qs, user):
    """Portefeuille personnel : CA = ses dossiers ; sinon agent affecté."""
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    names = user_capabilities(user)
    q = Q(assigned_to=user)
    if RELATIONSHIP_MANAGER in names and not is_finflow_admin(user):
        q |= officers_own_cases_q(user)
    return qs.filter(q)


def is_officers_case(user, case: CollectionCase) -> bool:
    """Dossier instruit / soumis par le chargé d'affaires."""
    application = getattr(getattr(case, "loan", None), "application", None)
    if application is None:
        return False
    if getattr(application, "submitted_by_id", None) == user.id:
        return True
    return getattr(application, "created_by_id", None) == user.id


def is_agency_case(user, case: CollectionCase) -> bool:
    application = getattr(getattr(case, "loan", None), "application", None)
    if application is None:
        return False
    agency_id = getattr(application, "agency_id", None)
    if not agency_id:
        return False
    return agency_id in get_user_agency_ids(user)


def case_owner_kind(case: CollectionCase) -> str:
    tranche = getattr(case, "tranche", None)
    if tranche is None:
        return CollectionTranche.OwnerKind.GESTIONNAIRE
    return tranche.owner_kind or CollectionTranche.OwnerKind.GESTIONNAIRE


def can_operate_collection_case(user, case: CollectionCase) -> bool:
    """Écriture opérationnelle (hors dialogue) sur le dossier."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active or (not user.is_group_level and user.tenant_id != case.tenant_id):
        return False
    if is_finflow_admin(user):
        return True
    if case.stage == CollectionCase.Stage.CLOSED:
        return False
    names = user_capabilities(user)
    kind = case_owner_kind(case)
    if kind == CollectionTranche.OwnerKind.GESTIONNAIRE:
        if COLLECTION_MANAGER in names:
            return True
        if AGENCY_MANAGER in names and is_agency_case(user, case):
            return True
        if RELATIONSHIP_MANAGER in names and is_officers_case(user, case):
            return True
        return False
    if kind == CollectionTranche.OwnerKind.COLLECTION:
        return bool(names & _COLLECTION_ROLES)
    if kind == CollectionTranche.OwnerKind.LEGAL:
        return bool(names & _LEGAL_ROLES)
    return False


def can_comment_collection_case(user, case: CollectionCase) -> bool:
    """Le dialogue est ouvert à tout utilisateur qui voit le dossier."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return True


def can_edit_authored(user, obj) -> bool:
    """Admin : tout. Sinon : auteur + droit d'opérer le dossier."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_finflow_admin(user):
        return True
    case = getattr(obj, "case", None)
    if case is None:
        loan = getattr(obj, "loan", None)
        case = getattr(loan, "collection_case", None) if loan is not None else None
    if case is not None and not can_operate_collection_case(user, case):
        return False
    return getattr(obj, "created_by_id", None) == user.id


def require_case_operate(user, case: CollectionCase) -> None:
    if not can_operate_collection_case(user, case):
        raise PermissionDenied(_DENY_OPERATE)


def can_edit_dialogue(user, obj) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_finflow_admin(user):
        return True
    return getattr(obj, "created_by_id", None) == user.id


def require_authored_edit(user, obj) -> None:
    if not can_edit_authored(user, obj):
        raise PermissionDenied(_DENY_EDIT_OWN)


def require_dialogue_edit(user, obj) -> None:
    if not can_edit_dialogue(user, obj):
        raise PermissionDenied(_DENY_EDIT_OWN)


def users_for_tranche_owner(tenant_id, owner_kind, case=None):
    """Utilisateurs habilités à opérer une tranche (avec e-mail)."""
    from django.db.models import Q

    from apps.accounts.models import User
    from apps.common.access import get_user_agency_ids

    kind = owner_kind or CollectionTranche.OwnerKind.GESTIONNAIRE
    if kind == CollectionTranche.OwnerKind.COLLECTION:
        names = _COLLECTION_ROLES
    elif kind == CollectionTranche.OwnerKind.LEGAL:
        names = _LEGAL_ROLES
    else:
        names = frozenset({
            RELATIONSHIP_MANAGER,
            AGENCY_MANAGER,
            COLLECTION_MANAGER,
        })
    qs = (
        users_with_capability(User.objects.filter(is_active=True), *names)
        .filter(Q(tenant_id=tenant_id) | Q(is_group_level=True))
        .exclude(email="")
        .distinct()
    )
    if kind != CollectionTranche.OwnerKind.GESTIONNAIRE:
        return [user for user in qs if user_capabilities(user) & names]

    app = getattr(getattr(case, "loan", None), "application", None) if case else None
    officer_ids = set()
    if app is not None:
        if getattr(app, "submitted_by_id", None):
            officer_ids.add(app.submitted_by_id)
        if getattr(app, "created_by_id", None):
            officer_ids.add(app.created_by_id)
    agency_id = getattr(app, "agency_id", None) if app is not None else None
    selected = []
    for user in qs:
        roles = user_capabilities(user)
        if COLLECTION_MANAGER in roles:
            selected.append(user)
            continue
        if RELATIONSHIP_MANAGER in roles and user.id in officer_ids:
            selected.append(user)
            continue
        if AGENCY_MANAGER in roles and agency_id:
            if agency_id in get_user_agency_ids(user):
                selected.append(user)
    return selected


def filter_visible_collection_cases(qs, user):
    """Périmètre de lecture : CA = ses dossiers ; chef = son agence."""
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_finflow_admin(user):
        return qs
    names = user_capabilities(user)
    if names & _BROAD_VIEW_ROLES:
        return qs
    if AGENCY_MANAGER in names:
        agency_ids = get_user_agency_ids(user)
        if not agency_ids:
            return qs.none()
        return qs.filter(loan__application__agency_id__in=agency_ids)
    if RELATIONSHIP_MANAGER in names:
        return qs.filter(officers_own_cases_q(user))
    return qs


def scoped_collection_cases(qs, user):
    """Périmètre lecture complet (data_scope + règles recouvrement)."""
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if getattr(user, "is_group_level", False) or is_finflow_admin(user):
        return filter_visible_collection_cases(qs, user)
    if uses_special_collection_scope(user):
        return filter_visible_collection_cases(qs, user)
    scope = getattr(user, "data_scope", DataScope.AGENCY)
    if scope == DataScope.AGENCY:
        agency_ids = get_user_agency_ids(user)
        if not agency_ids:
            return qs.none()
        qs = qs.filter(loan__application__agency_id__in=agency_ids)
    elif scope == DataScope.OWN:
        qs = qs.filter(assigned_to=user)
    return filter_visible_collection_cases(qs, user)


def filter_qs_by_visible_case(qs, user, case_field="case"):
    visible = scoped_collection_cases(CollectionCase.objects.all(), user)
    return qs.filter(**{f"{case_field}__in": visible})


def scoped_loan_decisions(qs, user):
    """Restructures / write-offs : même périmètre que les dossiers visibles."""
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if getattr(user, "is_group_level", False) or is_finflow_admin(user):
        return qs
    agency_ids = get_user_agency_ids(user)
    scope = getattr(user, "data_scope", DataScope.AGENCY)
    # Chef / staff filiale sans agence : lecture tenant (tests + profil TENANT).
    if not agency_ids and scope == DataScope.TENANT:
        return qs
    visible = scoped_collection_cases(CollectionCase.objects.all(), user)
    q = Q(loan__collection_case__in=visible)
    field_names = {f.name for f in qs.model._meta.get_fields()}
    if "case" in field_names:
        q |= Q(case__in=visible)
        orphan = Q(case__isnull=True, loan__collection_case__isnull=True)
        if agency_ids:
            q |= orphan & Q(loan__application__agency_id__in=agency_ids)
        elif scope == DataScope.OWN:
            q |= orphan & (
                Q(loan__application__created_by=user)
                | Q(loan__application__submitted_by=user)
            )
        elif uses_special_collection_scope(user) or (
            user_capabilities(user) & _BROAD_VIEW_ROLES
        ):
            q |= orphan
    return qs.filter(q)
