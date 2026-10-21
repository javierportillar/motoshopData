"""Invoice (POS sale) subsystem — slice 3 backend.

Legacy parity: `facventas` (header, NO primary key — the doc identity is
``(codclas, prefven, numfven)``), `detfventas` (1:N lines), `detapago` (1:N
payments) and `detcuentas` (accounting causación). The save follows the φ0..φ4
sequence of :mod:`motoshop_api.erp.engine` (ADR-0008-03).
"""
