"""Regression checks for the repeatable local demonstration dataset."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from apps.collections.models import (
    CollectionAction,
    CollectionCase,
    CollectionStageHistory,
    LitigationFile,
)


def _row_counts(tables):
    with connection.cursor() as cursor:
        return {
            table: _count_table(cursor, table)
            for table in tables
        }


def _count_table(cursor, table):
    cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)}")
    return cursor.fetchone()[0]


@pytest.mark.django_db(transaction=True)
def test_rich_volume_seed_is_repeatable_and_has_complete_loan_schedules(tmp_path):
    tables = (
        "credits_creditapplication",
        "credits_loan",
        "credits_installment",
        "collections_collectioncase",
        "collections_collectionaction",
        "collections_collectionstagehistory",
        "collections_litigationfile",
        "notifications_notificationlog",
        "guarantees_guarantee",
        "guarantees_dationrequest",
        "guarantees_guaranteereleaserequest",
        "sureties_surety",
        "sureties_suretyengagement",
        "documents_document",
    )
    with override_settings(MEDIA_ROOT=tmp_path):
        call_command(
            "seed_demo",
            volume=True,
            count=20,
            verbosity=0,
            stdout=StringIO(),
        )
        first = _row_counts(tables)

        call_command(
            "seed_demo",
            volume=True,
            count=20,
            verbosity=0,
            stdout=StringIO(),
        )
        second = _row_counts(tables)

        differences = {
            table: (first[table], second[table])
            for table in tables
            if first[table] != second[table]
        }
        if differences:
            details = {
                "cases": list(
                    CollectionCase.all_tenants.order_by("-created_at").values(
                        "stage", "days_overdue", "loan__application__reference"
                    )[:6]
                ),
                "actions": list(
                    CollectionAction.all_tenants.order_by("-created_at").values(
                        "action_type", "action_date", "case__loan__application__reference"
                    )[:8]
                ),
                "history": list(
                    CollectionStageHistory.all_tenants.order_by("-created_at").values(
                        "from_stage", "to_stage", "reason",
                        "case__loan__application__reference",
                    )[:8]
                ),
                "litigation": list(
                    LitigationFile.all_tenants.order_by("-created_at").values(
                        "status", "case__loan__application__reference"
                    )[:8]
                ),
            }
            assert second == first, {"differences": differences, **details}
        assert first["credits_loan"] >= 15
        assert first["credits_installment"] >= first["credits_loan"] * 3
        assert first["collections_collectioncase"] >= 15
        assert first["documents_document"] >= 20
