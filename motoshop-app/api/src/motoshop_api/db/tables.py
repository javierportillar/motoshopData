"""Definiciones de tablas SQLAlchemy Core (solo lectura en F1)."""

from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table

metadata = MetaData(schema="motoshop2024")

# Tablas reflejadas/declaradas para F1.
# Nota: MyISAM no tiene FKs; los tipos sonstring porque
# dump_to_cloud.py guarda todo como string en Parquet.

productos = Table(
    "productos",
    metadata,
    Column("codprod", String(20), primary_key=True),
    Column("nomprod", String(200)),
    Column("codsubp", String(10)),
    extend_existing=True,
)

auxinventario = Table(
    "auxinventario",
    metadata,
    Column("codprod", String(20)),
    Column("codbod", String(4)),
    Column("canactu", String(20)),
    extend_existing=True,
)

bodegas = Table(
    "bodegas",
    metadata,
    Column("codbod", String(4), primary_key=True),
    Column("nombod", String(100)),
    extend_existing=True,
)

facventas = Table(
    "facventas",
    metadata,
    Column("numnum", String(20)),
    Column("fecdoc", String(30)),
    Column("nitter", String(15)),
    Column("estdoc", String(1)),
    Column("codpag", String(4)),
    Column("valtotal", String(20)),
    extend_existing=True,
)

detfventas = Table(
    "detfventas",
    metadata,
    Column("numnum", String(20)),
    Column("codprod", String(20)),
    Column("cantidad", String(20)),
    Column("valunit", String(20)),
    Column("valtotal", String(20)),
    Column("fecdoc", String(30)),
    extend_existing=True,
)

terceros = Table(
    "terceros",
    metadata,
    Column("nitter", String(15), primary_key=True),
    Column("nomter", String(200)),
    Column("telter", String(30)),
    Column("emailter", String(100)),
    extend_existing=True,
)

sucursales = Table(
    "sucursales",
    metadata,
    Column("codsuc", String(4), primary_key=True),
    Column("nomsuc", String(100)),
    extend_existing=True,
)

formapago = Table(
    "formapago",
    metadata,
    Column("codpag", String(4), primary_key=True),
    Column("nompag", String(100)),
    extend_existing=True,
)
