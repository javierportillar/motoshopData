# C-1 · Stock real desde auxinventario — 2026-05-28

Notebook/endpoint: `GET /products/MOTS1297/stock`
SKU de prueba: **MOTS1297** ("ACEITE CASTROS 20 W 50")

## Respuesta de la API
```json
{
  "sku": "MOTS1297",
  "nomprod": "ACEITE CASTROS 20 W 50",
  "total": 691.0,
  "by_bodega": [
    {
      "codbod": "",
      "nombod": "",
      "cantidad": 691.0
    }
  ]
}
```

## SQL directo en MySQL
```sql
SELECT codprod, COUNT(*), SUM(valor3)
FROM auxinventario
WHERE codprod = 'MOTS1297'
GROUP BY codprod;
```
Resultado: `('MOTS1297', 640, 691.0)`

## Cuadre
- API total: **691.0**
- SQL SUM(valor3): **691.0**
- OK - cuadran 1:1 para este SKU.

## Nota
La columna `auxinventario.codbod` está vacía en la BD actual, así que el desglose por bodega queda sin nombre. El total, sin embargo, sí cuadra con SQL directo.
