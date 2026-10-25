"""Permission contracts for after-sales request workflows."""
from types import SimpleNamespace

import pytest

from apps.common.permissions import HasModelPermission
from apps.guarantees.views import (
    DationRequestViewSet,
    GuaranteeFormalizationRequestViewSet,
    GuaranteeReleaseRequestViewSet,
)


AFTER_SALES_VIEWSETS = [
    (GuaranteeReleaseRequestViewSet, "guarantees.view_guaranteereleaserequest", "guarantees.initiate_guaranteereleaserequest"),
    (DationRequestViewSet, "guarantees.view_dationrequest", "guarantees.initiate_dationrequest"),
    (GuaranteeFormalizationRequestViewSet, "guarantees.view_guaranteeformalizationrequest", "guarantees.initiate_guaranteeformalizationrequest"),
]


def _user_with(permission):
    def has_perm(codename):
        return codename == permission

    return SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_superuser=False,
        must_change_password=False,
        has_perm=has_perm,
        has_perms=lambda codenames: all(has_perm(codename) for codename in codenames),
    )


@pytest.mark.parametrize("viewset,view_perm,initiate_perm", AFTER_SALES_VIEWSETS)
def test_process_view_permission_also_allows_initiators_to_follow_requests(
    viewset, view_perm, initiate_perm
):
    permission = HasModelPermission()
    view = viewset()
    user = _user_with(initiate_perm)

    for action in ("list", "retrieve", "workflow"):
        view.action = action
        assert permission.has_permission(
            SimpleNamespace(user=user, method="GET"), view
        )

    view.action = "documents"
    assert permission.has_permission(
        SimpleNamespace(user=user, method="GET"), view
    )
    assert permission.has_permission(
        SimpleNamespace(user=user, method="POST"), view
    )

    read_only_user = _user_with(view_perm)
    assert permission.has_permission(
        SimpleNamespace(user=read_only_user, method="GET"), view
    )
    assert not permission.has_permission(
        SimpleNamespace(user=read_only_user, method="POST"), view
    )
