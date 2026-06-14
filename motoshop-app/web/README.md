# motoshop-web — MOVIDO

> **El frontend se mudó a su propio repo el 2026-06-14.**
>
> Ubicación nueva: **https://github.com/javierportillar/frontfambus**

El historial completo (commits, autores, fechas) está preservado en el repo nuevo: el primer commit allí es el mismo que el último de este directorio en este repo (`a3b5e90`).

## ¿Por qué se movió?

Para que el ciclo de deploy del frontend no dependa del backend. Vercel ahora deploya directo desde [`frontfambus`](https://github.com/javierportillar/frontfambus) por su integración nativa con GitHub.

## Para el dev front

```bash
git clone https://github.com/javierportillar/frontfambus.git
cd frontfambus
npm install
cp .env.local.example .env.local
npm run dev
```

## ¿Por qué este directorio sigue existiendo?

Respaldo temporal hasta que se valide el primer deploy desde [`frontfambus`](https://github.com/javierportillar/frontfambus). Una vez confirmado, se borra todo el directorio `motoshop-app/web/` con un commit final.

**No edites código acá** — cualquier cambio acá NO llega a producción. Trabajá en [`frontfambus`](https://github.com/javierportillar/frontfambus).
