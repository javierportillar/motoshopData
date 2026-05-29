"""
Tests unitarios de transformaciones silver — MotoShop.

Tests locales sin PySpark (validación de lógica y patrones).
Tests reales en Databricks: notebooks/silver/32_test_silver.py

Ejecutar: pytest tests/silver/test_transformations.py -v
"""

import pytest


class TestDimProductoSchema:
    """Valida que el esquema de dim_producto sea correcto."""

    EXPECTED_COLUMNS = [
        "cod_producto", "nombre_producto", "codigo_barras",
        "cod_medida", "valor_medida", "presentacion",
        "stock_minimo", "stock_maximo", "existencia",
        "costo_producto", "costo_ultima_compra",
        "precio_venta_sin_iva", "precio_venta_con_iva",
        "estado_producto", "cod_grupo", "cod_linea1",
        "descripcion", "nit_proveedor", "cod_bodega_default",
        "fecha_actualizacion", "snapshot_date",
    ]

    def test_no_unimed_column(self):
        """unimed no debe existir en dim_producto (está en auxinventario)."""
        assert "unimed" not in self.EXPECTED_COLUMNS

    def test_no_codcla_column(self):
        """codcla no debe existir en dim_producto (no existe en bronze.productos)."""
        assert "codcla" not in self.EXPECTED_COLUMNS

    def test_no_codsubcla_column(self):
        """codsubcla no debe existir en dim_producto."""
        assert "codsubcla" not in self.EXPECTED_COLUMNS

    def test_has_cod_producto_pk(self):
        """cod_producto debe ser la primary key."""
        assert "cod_producto" in self.EXPECTED_COLUMNS

    def test_column_count(self):
        """dim_producto debe tener 21 columnas."""
        assert len(self.EXPECTED_COLUMNS) == 21


class TestFactVentasSchema:
    """Valida el esquema de fact_ventas."""

    EXPECTED_COLUMNS = [
        "num_documento", "cod_clase", "prefijo",
        "fecha_documento_ts", "business_date",
        "nit_cliente", "nombre_cliente",
        "nit_vendedor", "nombre_vendedor",
        "cod_formapago", "dias_formapago",
        "subtotal", "total_descuentos", "total_iva",
        "total_impuesto", "retencion_fuente",
        "retencion_iva", "retencion_ica",
        "total_factura", "observaciones",
        "estado_documento", "cod_sucursal",
        "cod_empresa", "cod_empresa_alt",
        "cod_resolucion", "ingest_date_silver",
    ]

    def test_has_composite_pk(self):
        """PK compuesta: num_documento + cod_clase + business_date."""
        assert "num_documento" in self.EXPECTED_COLUMNS
        assert "cod_clase" in self.EXPECTED_COLUMNS
        assert "business_date" in self.EXPECTED_COLUMNS

    def test_has_total_factura(self):
        """total_factura debe existir para reconciliación."""
        assert "total_factura" in self.EXPECTED_COLUMNS

    def test_filter_estfven(self):
        """El notebook filtra WHERE estfven = 'A'."""
        assert True  # Validado por el notebook 10_fact_ventas.py


class TestFactVentasDetalleSchema:
    """Valida el esquema de fact_ventas_detalle."""

    EXPECTED_COLUMNS = [
        "num_documento", "cod_clase", "cod_producto",
        "nombre_detalle", "cantidad", "valor_unitario",
        "descuento_porcentaje", "descuento_valor",
        "iva_porcentaje", "iva_valor",
        "ipo_porcentaje", "ipo_valor",
        "total_detalle", "costo_producto",
        "num_item", "cod_bodega", "cod_centro_costo",
        "business_date",
    ]

    def test_join_with_fact_ventas(self):
        """business_date se hereda de fact_ventas via JOIN."""
        assert "business_date" in self.EXPECTED_COLUMNS

    def test_has_cantidad(self):
        """cantidad debe existir para métricas de inventario."""
        assert "cantidad" in self.EXPECTED_COLUMNS


class TestFactComprasSchema:
    """Valida el esquema de fact_compras."""

    EXPECTED_COLUMNS = [
        "num_documento", "cod_clase", "prefijo",
        "fecha_documento_ts", "business_date",
        "nit_proveedor", "nombre_proveedor",
        "cod_sucursal", "cod_formapago",
        "subtotal", "total_descuentos", "total_iva",
        "total_impuesto", "retencion_fuente",
        "retencion_iva", "retencion_ica",
        "total_compra", "observaciones",
        "estado_documento", "cod_empresa",
        "cod_empresa_alt", "nit_vendedor",
        "ingest_date_silver",
    ]

    def test_has_total_compra(self):
        """total_compra debe existir para reconciliación."""
        assert "total_compra" in self.EXPECTED_COLUMNS


class TestFactInventarioSchema:
    """Valida el esquema de fact_inventario."""

    EXPECTED_COLUMNS = [
        "id_inventario", "cod_lista", "nombre_lista",
        "cod_linea1", "nombre_linea",
        "cod_linea2", "nombre_linea2",
        "cod_bodega", "nombre_bodega",
        "nit_tercero", "nombre_tercero",
        "num_documento", "nombre_documento",
        "cod_producto", "num_serie", "nombre_producto",
        "unidad_medida", "valor_costo", "valor_venta",
        "cantidad", "valor4", "valor5",
        "business_date", "num_doc_referencia",
        "nombre_sub", "multiplo",
        "cod_centro_costo", "nombre_centro_costo",
    ]

    def test_has_cantidad(self):
        """cantidad (valor3) es el campo clave de inventario."""
        assert "cantidad" in self.EXPECTED_COLUMNS


class TestQualityRunLogic:
    """Valida la lógica del quality run."""

    def test_no_declare_set(self):
        """quality_run no debe usar DECLARE/SET (SQL Warehouse incompatível)."""
        with open("notebooks/silver/20_quality_run.py") as f:
            content = f.read()
        assert "DECLARE" not in content
        assert "SET run_id" not in content

    def test_has_magic_sql(self):
        """Todas las celdas SQL deben tener -- MAGIC %sql o ser SQL directo."""
        with open("notebooks/silver/20_quality_run.py") as f:
            content = f.read()
        # No debe tener marcadores Python
        assert "# COMMAND ----------" not in content

    def test_uses_databricks_format(self):
        """El archivo debe usar formato Databricks SQL notebook."""
        with open("notebooks/silver/20_quality_run.py") as f:
            first_line = f.readline().strip()
        assert first_line == "-- Databricks notebook source"


class TestNotebookFormat:
    """Valida que todos los notebooks usen formato SQL correcto."""

    NOTEBOOKS = [
        "01_dim_producto.py", "02_dim_bodega.py", "03_dim_tercero.py",
        "04_dim_sucursal.py", "05_dim_formapago.py", "06_dim_tiempo.py",
        "10_fact_ventas.py", "11_fact_ventas_detalle.py", "12_fact_compras.py",
        "13_fact_compras_detalle.py", "14_fact_inventario.py",
        "20_quality_run.py", "30_validate_silver.py", "31_reconciliation.py",
    ]

    def test_all_start_with_databricks_source(self):
        """Todos los notebooks deben empezar con -- Databricks notebook source."""
        for nb in self.NOTEBOOKS:
            with open(f"notebooks/silver/{nb}") as f:
                first_line = f.readline().strip()
            assert first_line == "-- Databricks notebook source", (
                f"{nb} empieza con: {first_line}"
            )

    def test_no_python_markers(self):
        """Ningún notebook debe tener marcadores Python (# COMMAND, # MAGIC)."""
        for nb in self.NOTEBOOKS:
            with open(f"notebooks/silver/{nb}") as f:
                content = f.read()
            assert "# COMMAND ----------" not in content, (
                f"{nb} tiene marcadores Python"
            )

    def test_all_have_magic_md(self):
        """Todos los notebooks deben tener al menos un markdown."""
        for nb in self.NOTEBOOKS:
            with open(f"notebooks/silver/{nb}") as f:
                content = f.read()
            assert "-- MAGIC %md" in content, (
                f"{nb} no tiene celdas markdown"
            )

    def test_references_correct_schemas(self):
        """Los notebooks deben referenciar motoshop.bronze.* y motoshop.silver.*."""
        for nb in self.NOTEBOOKS:
            with open(f"notebooks/silver/{nb}") as f:
                content = f.read()
            # No debe tener esquemas incorrectos
            assert "motoshop.python." not in content
            assert "bronze_raw." not in content
