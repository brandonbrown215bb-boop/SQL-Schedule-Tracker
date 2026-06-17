# DEVOPS-001: CI/CD Pipeline with GitHub Actions

**Status**: Draft  
**Priority**: High  
**Effort**: S (5 days)  
**Depends on**: None  

---

## Problem Statement

No automated CI/CD pipeline. All development work is local:

| Missing | Impact |
|---------|--------|
| Lint checks | Inconsistent code style, no type checking |
| Automated tests | Regressions not caught before merge |
| Build artifacts | Manual PyInstaller builds for distribution |
| Release management | Manual version tagging, no changelog |
| Pre-commit hooks | Lint issues committed to repo |

---

## Solution

GitHub Actions CI/CD pipeline with lint, test, build, and release stages.

### Pipeline Stages

```
┌─────────┐    ┌────────┐    ┌─────────┐    ┌──────────┐
│   Lint  │ →  │  Test  │ →  │  Build  │ →  │ Release  │
│ ruff +  │    │pytest +│    │PyInst. │    │GitHub    │
│ mypy    │    │3 Pyth. │    │ 3 OS   │    │Releases  │
└─────────┘    └────────┘    └─────────┘    └──────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
  Fail if      Fail if       Artifact:     Auto-tag +
  any lint     any test      .exe/.dmg/    changelog
  error        fails         .AppImage     generation
```

### Full Workflow

```yaml
# .github/workflows/ci.yml

name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  release:
    types: [published]

env:
  PYTHON_VERSION: "3.11"
  POETRY_VERSION: "1.7.0"

jobs:
  lint:
    name: Lint (ruff + mypy)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install ruff mypy
          pip install -r requirements.txt
      - name: ruff lint
        run: ruff check . --line-length=120
      - name: mypy type check
        run: mypy . --strict --ignore-missing-imports
      - name: ruff format check
        run: ruff format . --check --line-length=120

  test:
    name: Test (pytest)
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install system deps (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1-mesa libxkbcommon-x11-0
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-qt pytest-cov pytest-benchmark hypothesis
      - name: Run tests
        run: |
          python -m pytest tests/ -v --cov=./ --cov-report=xml \
            --benchmark-skip
        env:
          QT_QPA_PLATFORM: offscreen
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests

  build:
    name: Build (${{ matrix.os }})
    needs: [lint, test]
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install system deps (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1-mesa libxkbcommon-x11-0
      - name: Install PyInstaller
        run: pip install pyinstaller
      - name: Build with PyInstaller
        run: pyinstaller --onefile --windowed --name "UnitTracker" main.py
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: UnitTracker-${{ runner.os }}
          path: dist/UnitTracker*

  release:
    name: Release
    needs: [build]
    if: github.event_name == 'release'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Download all artifacts
        uses: actions/download-artifact@v4
      - name: Generate changelog
        id: changelog
        uses: heinrichreimer/github-changelog-generator-action@v2.3
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
      - name: Upload release assets
        uses: softprops/action-gh-release@v1
        with:
          files: |
            UnitTracker-*/*
          body: ${{ steps.changelog.outputs.changelog }}
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix, --line-length=120]
      - id: ruff-format
        args: [--line-length=120]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        args: [--strict, --ignore-missing-imports]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=500']
```

### Branch Protection Rules

Settings to apply to `main` branch on GitHub:

| Rule | Value |
|------|-------|
| Require PRs | Yes, at least 1 approval |
| Dismiss stale reviews | Yes |
| Require status checks | lint, test (linux), test (windows) |
| Require branches up-to-date | Yes |
| Include administrators | Yes |
| Allow force pushes | No |
| Allow deletions | No |

---

## Implementation Phases

### Phase 1: Pre-commit + Lint Pipeline (1 day)
1. Create `.pre-commit-config.yaml` with ruff and mypy
2. Create `.github/workflows/ci.yml` with lint job
3. Fix all existing lint errors
4. Add ruff configuration to `pyproject.toml`
5. `pip install pre-commit && pre-commit install`

### Phase 2: Test Pipeline (1 day)
1. Add test job to workflow (3 Python versions, 2 OS)
2. Add codecov upload
3. Fix platform-specific test failures (Windows paths, Qt offscreen)
4. **Verify**: Tests pass on all platforms

### Phase 3: Build Pipeline (2 days)
1. Add PyInstaller spec file
2. Add build job to workflow (3 OS)
3. Test binary: launch, connect to SQLite, verify main window
4. Add smoke test for built binary
5. **Verify**: Binary builds on all 3 OS

### Phase 4: Release Automation (1 day)
1. Configure auto-tagging on version bump
2. Add changelog generation
3. Add release asset upload
4. Document release process in CONTRIBUTING.md

---

## Success Criteria

1. Every PR runs lint + test pipeline; failure blocks merge
2. Tests pass on Python 3.10, 3.11, 3.12 on both Linux and Windows
3. Binaries build on all 3 platforms
4. Release creates GitHub Release with changelog and artifacts
5. Pre-commit catches lint errors before commit

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Pre-commit + Lint | 1 |
| Phase 2: Test Pipeline | 1 |
| Phase 3: Build Pipeline | 2 |
| Phase 4: Release Automation | 1 |
| **Total** | **5** |