"""Definiciones de tablas SQLAlchemy Core (solo lectura en F1)."""

from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table

metadata = MetaData(schema="motoshop2024")

productos = Table(
    "productos",
    metadata,
    Column("codprod", String(20), primary_key=True),
    Column("codbar", String(40)),
    Column("nomprod", String(200)),
    Column("codmed", String(3)),
    Column("valmed", String(20)),
    Column("presen", String(30)),
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
    Column("numfven", String(20)),
    Column("fecfven", String(30)),
    Column("nitter", String(15)),
    Column("estfven", String(1)),
    Column("codpag", String(4)),
    Column("totfven", String(20)),
    extend_existing=True,
)

detfventas = Table(
    "detfventas",
    metadata,
    Column("numfven", String(20)),
    Column("codprod", String(20)),
    Column("candet", String(20)),
    Column("valuni", String(20)),
    Column("nomdet", String(300)),
    extend_existing=True,
)

terceros = Table(
    "terceros",
    metadata,
    Column("nitter", String(15), primary_key=True),
    Column("nomter", String(30)),
    Column("razsoc", String(100)),
    Column("nomcom", String(120)),
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
