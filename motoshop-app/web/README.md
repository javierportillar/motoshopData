# motoshop-web

PWA Next.js 14 (App Router) de MotoShop (Track T).

## Requisitos

- Node 18.18+
- npm (o pnpm/yarn — usar uno solo de forma consistente)

## Setup local

```bash
cd motoshop-app/web
npm install
cp .env.local.example .env.local
npm run dev
```

Abrir http://localhost:3000.

## Scripts

- `npm run dev` — servidor de desarrollo (puerto 3000)
- `npm run build` — build de producción
- `npm run start` — servir el build
- `npm run lint` — ESLint
- `npm run typecheck` — TypeScript estricto (sin `any`)
- `npm run format` — Prettier

## Estado por fase

| Fase | Estado |
|------|--------|
| F0   | scaffold + página vacía |
| F1   | login JWT |
| F2   | búsqueda, ficha SKU, stock, instalable como PWA |
| F3+  | ver `PLAN.md` |
