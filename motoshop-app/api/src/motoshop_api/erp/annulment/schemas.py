"""Annulment request schema (slice 5 — spec erp-document-annulment).

The client sends only the facts the server cannot know: WHY the document is
being annulled. Everything else is server-owned:

- the document class/number travel in the path
  (``POST /api/erp/documents/{codclas}/{numfven}/annulment``);
- the annulment date, the hour, the company and the audit row are stamped by
  the server (``motanudoc.fecanu``/``horanu``/``codemp``);
- the flag inversion, the stock recomputation and the journal mirror are
  derived from the legacy rows.

``motivo`` is MANDATORY (legacy ``FrModAnuDoc``: the reason is required), but
it is validated as a BUSINESS rule inside the repo so the failure is the
aggregate 422 body naming the offending field — never a pydantic shape error.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Legacy ``motanudoc.motanu`` truncation (code_analysis §7.8 — the reason is
#: stored truncated to 800 chars).
MOTANU_MAX_LEN = 800


class AnnulmentRequest(BaseModel):
    """POST /api/erp/documents/{codclas}/{numfven}/annulment body."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(default="", max_length=4000)
