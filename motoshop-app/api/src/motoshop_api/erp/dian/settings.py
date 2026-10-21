"""DIAN provider configuration (task 6.x — operator onboarding).

The electronic invoicing is provider-agnostic: the ERP talks to a
``DianAdapter`` (see ``adapter.py``) and the operator chooses the provider
with the environment. Until the provider account exists, the STUB adapter
is used and the document stays ``PENDING`` — the legacy behaviour
(``contadores.envfele = 'S'``) is preserved: a document is only editable
while it has not been accepted by the DIAN (``estfele`` 1/2).

Environment (add to ``motoshop-app/api/.env``):

    DIAN_PROVIDER=dataico          # dataico | softprop | stub
    DIAN_API_BASE=https://api.dataico.com/direct/dataico_api/v2
    DIAN_API_TOKEN=                # bearer/token of the provider account
    DIAN_API_KEY=                  # client key (Dataico) or shared key
    DIAN_API_SECRET=               # client secret (Dataico)
    DIAN_TIMEOUT_SECONDS=30

The legacy side is configured in the ``sgHermes`` database:

    ``provetecno``  -> the technological provider of the company
    ``formapago.codfele`` -> the payment forms that issue electronic documents
    ``contadores.envfele = 'S'`` -> the numbering window for electronic docs
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DianSettings:
    """The provider selection and its credentials (from the environment)."""

    provider: str = "stub"
    api_base: str = ""
    api_token: str = ""
    api_key: str = ""
    api_secret: str = ""
    timeout_seconds: int = 30

    @property
    def is_live(self) -> bool:
        """A live provider needs a base URL and a credential."""
        return self.provider not in {"", "stub"} and bool(self.api_base)

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_token or self.api_key)


def get_dian_settings() -> DianSettings:
    """Read the provider configuration from the environment."""
    return DianSettings(
        provider=os.getenv("DIAN_PROVIDER", "stub").strip().lower(),
        api_base=os.getenv("DIAN_API_BASE", "").strip(),
        api_token=os.getenv("DIAN_API_TOKEN", "").strip(),
        api_key=os.getenv("DIAN_API_KEY", "").strip(),
        api_secret=os.getenv("DIAN_API_SECRET", "").strip(),
        timeout_seconds=int(os.getenv("DIAN_TIMEOUT_SECONDS", "30") or 30),
    )


def get_dian_adapter():
    """The adapter for the configured provider (the stub when not configured).

    The stub is the default on purpose: without a provider account the ERP
    must keep working exactly like the legacy desktop did - the document is
    queued, the CUFE stays empty and the document remains editable.
    """
    from motoshop_api.erp.dian.adapter import DianStubAdapter
    from motoshop_api.erp.dian.live_adapters import (
        DianDataicoAdapter,
        DianSoftPropAdapter,
    )

    settings = get_dian_settings()
    if not settings.is_live:
        return DianStubAdapter()
    if settings.provider == "dataico":
        return DianDataicoAdapter(settings)
    if settings.provider == "softprop":
        return DianSoftPropAdapter(settings)
    return DianStubAdapter()
