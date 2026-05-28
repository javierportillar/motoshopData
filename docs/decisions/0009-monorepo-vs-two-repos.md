# ADR-0009 · Monorepo vs. dos repos separados

- **Estado:** Accepted (provisional, revisable en F6)
- **Fecha:** 2026-05-27
- **Bloquea:** F0 (estructura del repo)
- **Decide:** Agente, con visto bueno implícito al aceptar F0

## Contexto

El PLAN.md §17 prevé dos repos: `motoshopdata` (analítica) y `motoshop-app` (API + PWA). Hoy existe solo `motoshopData` con el `.git` ya inicializado y sin código aún. Mantener dos repos desde el día 1 implica overhead de sincronizar versiones, duplicar CI y manejar dos historiales para un equipo de una persona.

## Opciones consideradas

1. **Monorepo:** `motoshop-app/` como subdirectorio de `motoshopData/`.
2. **Dos repos separados** desde el inicio (lo que prevé PLAN §17).

## Decisión

Adoptar **monorepo** (1). El proyecto está en F0 con un único responsable; dos repos serían overhead sin valor. En F6, cuando se discuta CI/CD y entornos separados, se reevalúa.

## Consecuencias

- Track A y Track T comparten historial, issues y CI.
- Cada track mantiene su propio `pyproject.toml` / `package.json` para que el setup sea independiente.
- Si en F6 se decide separar: `git filter-repo` permite extraer `motoshop-app/` a su propio repo conservando historial.
- El `.gitignore` raíz cubre ambos tracks; cada track puede añadir el suyo si hace falta.
