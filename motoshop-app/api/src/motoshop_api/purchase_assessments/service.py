"""Bounded, retryable background backfill and post-snapshot assessment processing."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from motoshop_api.purchase_assessments.analyzer import (
    ANALYZER_REVISION,
    PurchaseInvoice,
    analyze_purchase_invoice,
    discover_purchase_invoices,
)
from motoshop_api.purchase_assessments.generator import (
    PROMPT_REVISION,
    generate_assessment_markdown,
)
from motoshop_api.purchase_assessments.repository import (
    PurchaseAssessmentRepository,
    get_purchase_assessment_repository,
)

logger = logging.getLogger(__name__)

ASSESSMENT_START_DATE = date(2026, 9, 1)
DISCOVERY_PAGE_SIZE = 50
PROCESSING_BATCH_SIZE = 5


def assessment_fingerprint(
    invoice: PurchaseInvoice,
    metrics: dict[str, Any],
) -> str:
    """Hash stable invoice/evidence facts while excluding cutoff dates by themselves."""
    evidence = {key: value for key, value in metrics.items() if key != "source_cutoffs"}
    canonical = {
        "invoice_content_fingerprint": invoice.content_fingerprint,
        "invoice_facts": metrics.get("invoice", {}),
        "deterministic_evidence": evidence,
        "analyzer_revision": ANALYZER_REVISION,
        "prompt_revision": PROMPT_REVISION,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _assessment_row(
    tenant_id: str,
    invoice: PurchaseInvoice,
    metrics: dict[str, Any],
    evidence_fingerprint: str,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "business_date": invoice.business_date.isoformat(),
        "cod_clase": invoice.cod_clase,
        "num_documento": invoice.num_documento,
        "nit_proveedor": metrics["invoice"].get("nit_proveedor"),
        "nombre_proveedor": metrics["invoice"].get("nombre_proveedor"),
        "content_fingerprint": invoice.content_fingerprint,
        "assessment_fingerprint": evidence_fingerprint,
        "status": "pending",
        "attempt_count": 0,
        "deterministic_metrics": metrics,
        "source_cutoffs": metrics.get("source_cutoffs", {}),
        "analyzer_revision": ANALYZER_REVISION,
        "prompt_revision": PROMPT_REVISION,
    }


def _decode_metrics(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("deterministic_metrics") or {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("invalid_deterministic_metrics")
    return value


def _process_pending_assessments(
    tenant_id: str,
    store: PurchaseAssessmentRepository,
    llm_client: Any | None,
) -> tuple[int, int]:
    generated = 0
    failed = 0
    try:
        candidates = store.list_claimable(tenant_id, PROCESSING_BATCH_SIZE)
    except Exception as exc:
        logger.warning(
            "Purchase assessment queue unavailable tenant=%s error_type=%s",
            tenant_id,
            type(exc).__name__,
        )
        return generated, 1
    for candidate in candidates:
        claimed = store.claim(candidate)
        if claimed is None:
            continue
        row_id = str(claimed.get("id") or "")
        claim_token = str(claimed.get("claim_token") or "")
        try:
            metrics = _decode_metrics(claimed)
            report = generate_assessment_markdown(
                metrics,
                llm_client=llm_client,
                tenant_id=tenant_id,
            )
            if not store.complete(tenant_id, row_id, claim_token, report):
                continue
            generated += 1
        except Exception as exc:
            failed += 1
            with suppress(Exception):
                store.fail(
                    tenant_id,
                    row_id,
                    claim_token,
                    type(exc).__name__,
                    int(claimed.get("attempt_count") or 1),
                )
            logger.warning(
                "Purchase assessment processing failed tenant=%s error_type=%s",
                tenant_id,
                type(exc).__name__,
            )
    return generated, failed


def refresh_purchase_assessments(
    tenant_id: str,
    db_path: str | Path,
    *,
    repository: PurchaseAssessmentRepository | None = None,
    llm_client: Any | None = None,
    reset_cursor: bool = True,
) -> dict[str, int]:
    """Discover invoice changes, atomically claim work, and persist bounded reports.

    Intended for a FastAPI ``BackgroundTasks`` call after a successful snapshot
    publication. Storage/provider failures never change the already-successful
    admin refresh response.
    """
    store = repository or get_purchase_assessment_repository()
    discovered = 0
    try:
        connection = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        logger.warning(
            "Purchase assessment snapshot unavailable tenant=%s error_type=%s",
            tenant_id,
            type(exc).__name__,
        )
        generated, failed = _process_pending_assessments(tenant_id, store, llm_client)
        return {"discovered": 0, "generated": generated, "failed": failed}

    try:
        if reset_cursor:
            store.reset_scan_cursor(tenant_id)
        cursor = store.get_scan_cursor(tenant_id)
        inventory_source = "catalog" if tenant_id.casefold() == "masvital" else "gold"
        after = (date.fromisoformat(cursor[0]), cursor[1], cursor[2]) if cursor else None
        invoices = discover_purchase_invoices(
            connection,
            ASSESSMENT_START_DATE,
            limit=DISCOVERY_PAGE_SIZE,
            after=after,
        )
        if not invoices:
            store.advance_scan_cursor(tenant_id, cursor, None)
            invoices = []
        pending_rows: list[dict[str, Any]] = []
        for invoice in invoices:
            metrics = analyze_purchase_invoice(
                connection,
                invoice,
                inventory_source=inventory_source,
            )
            evidence_fingerprint = assessment_fingerprint(invoice, metrics)
            pending_rows.append(
                _assessment_row(tenant_id, invoice, metrics, evidence_fingerprint)
            )
        discovered = store.insert_pending(pending_rows)
        if invoices:
            last_invoice = invoices[-1]
            store.advance_scan_cursor(
                tenant_id,
                cursor,
                (
                    last_invoice.business_date.isoformat(),
                    last_invoice.cod_clase,
                    last_invoice.num_documento,
                ),
            )

    except Exception as exc:
        logger.warning(
            "Purchase assessment batch failed tenant=%s error_type=%s",
            tenant_id,
            type(exc).__name__,
        )
    finally:
        connection.close()
    generated, failed = _process_pending_assessments(tenant_id, store, llm_client)
    return {"discovered": discovered, "generated": generated, "failed": failed}
