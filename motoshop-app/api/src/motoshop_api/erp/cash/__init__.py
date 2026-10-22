"""Collections & cash write path (slice 4 — spec erp-collections-cash).

Modules:
- ``schemas``  request payloads (receipts, cash movements, arqueo, consignment)
- ``store``    legacy row access (Fake twin + real MySQL writer)
- ``repo``     the save repos (φ0..φ4 sequence, ADR-0008-03)
- ``router``   HTTP endpoints under ``/api/erp`` (matrix-gated)

Legacy parity lives here: ``Graba_Fpago`` duality (soldeb/solcre by tipclas),
the live CxC balance (``SUM(detcuentas.valdeb − valhab)`` on the cartera
accounts: the canonical ``13050501`` and its legacy alias ``1305``),
``Hay_Cie_Eli`` period lock, ``cajaarqueo``/``detcajarq`` arqueo
invariants and the ``consbancab`` bank counter (``formapago.numcon``).
"""

from __future__ import annotations
