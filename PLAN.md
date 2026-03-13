# Promote Python Pipeline to Root; Archive R Code

## Context
Repo at `/Users/michaelaydinbas/git/github/pmayd/a4d` has two pipelines:
Python pipeline in `a4d-python/` (active, deployed), R pipeline at root (legacy).
Python pipeline is production-deployed and working on branch `migration`.

## Problem
Python pipeline is buried in a subdirectory making it a second-class citizen.
R pipeline clutters root. Need to invert this structure.

## Approach
Move `a4d-python/` contents to repo root; move R files to `r-archive/`.
Keep `reference_data/` at root (shared, unchanged).
Work directly on `migration` branch, targeting merge to `dev`.

## Non-goals
- No changes to `reference_data/` content
- No changes to R pipeline logic
- No changes to Cloud Run deployment config (`A4D_REFERENCE_DATA` env var handles paths)
- No new CI/CD for R pipeline

## Tasks

### Phase 1 — Archive R Code
1. Create `r-archive/` and move R files into it: `R/`, `scripts/R/`, `tests/`,
   `man/`, `renv/`, `renv.lock`, `a4d.Rproj`, `DESCRIPTION`, `NAMESPACE`,
   `.lintr`, `.Rbuildignore`, `.Rprofile`, `readme.md`
2. Update root `.gitignore`: remove R-specific entries (renv/, etc.), merge with `a4d-python/.gitignore`
3. Delete `.github/workflows/test-coverage.yaml` (R CI, no longer needed)

### Phase 2 — Promote Python Pipeline
4. Move `a4d-python/` contents to root: `src/`, `tests/`, `docs/`, `scripts/`,
   `pyproject.toml`, `uv.lock`, `justfile`, `Dockerfile`, `README.md`,
   `SETUP.md`, `.env.example`
5. Fix `src/a4d/reference/loaders.py:37`: `parents[4]` → `parents[3]`
6. Update `Dockerfile`: `COPY a4d-python/pyproject.toml ...` → `COPY pyproject.toml ...`,
   `COPY a4d-python/src/` → `COPY src/`
7. Update `.dockerignore`: strip `a4d-python/` prefixes from all entries
8. Update `justfile`: Docker build context `..` → `.`
9. Update `.github/workflows/python-ci.yml`: remove `a4d-python/` from path
   triggers, remove `working-directory: a4d-python`, fix coverage path
10. Update root `CLAUDE.md` to reflect new structure
11. Delete now-empty `a4d-python/` directory

### Phase 3 — Verify & Cleanup
12. Run `uv run pytest` from repo root — all tests must pass
13. Build Docker image locally (`just docker-build`) — must succeed
14. Confirm `reference_data/` is resolved correctly in tests without env var override

## Done when
- `uv run pytest` passes from repo root (no `cd a4d-python` required)
- `just docker-build` succeeds with updated build context
- `reference_data/` resolves correctly in tests via `loaders.py`
- `r-archive/` contains all R files; no R files remain at repo root
- Python CI workflow triggers on `src/**`, `tests/**`, `pyproject.toml` path changes
- `a4d-python/` directory no longer exists

## Open questions
- None — all resolved before implementation.
