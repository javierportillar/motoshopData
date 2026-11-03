"""El cache de métricas tiene que estar acotado.

La clave incluye la generación del snapshot, así que cada refresco del gold desde
R2 estrena generación y las entradas viejas quedaban inalcanzables pero en
memoria. En el plan free de Render (512 MB) eso termina en "exceeded its memory
limit" y reinicio automático (2026-11-03).
"""

from __future__ import annotations

from motoshop_api.metrics import router as metrics


def setup_function() -> None:
    metrics._cache.clear()


def test_descarta_las_vencidas() -> None:
    ahora = 1_000.0
    for i in range(5):
        metrics._cache[(0, f"vieja-{i}")] = (ahora - 400, i)
    metrics._cache[(0, "nueva")] = (ahora, 1)

    metrics._podar_cache(ahora, metrics._CACHE_TTL)

    assert list(metrics._cache) == [(0, "nueva")]


def test_respeta_el_techo_y_conserva_las_mas_nuevas() -> None:
    ahora = 10_000.0
    total = metrics._CACHE_MAX_ENTRIES + 44
    for i in range(total):
        metrics._cache[(0, f"k{i}")] = (ahora - i, i)  # k0 es la más nueva

    metrics._podar_cache(ahora, metrics._CACHE_TTL)

    assert len(metrics._cache) == metrics._CACHE_MAX_ENTRIES
    assert (0, "k0") in metrics._cache
    assert (0, f"k{total - 1}") not in metrics._cache


def test_si_no_hay_nada_vencido_y_sobra_poco_no_toca_nada() -> None:
    ahora = 5_000.0
    for i in range(3):
        metrics._cache[(0, f"k{i}")] = (ahora - i, i)

    metrics._podar_cache(ahora, metrics._CACHE_TTL)

    assert len(metrics._cache) == 3
