from __future__ import annotations

from pathlib import Path

from scripts.validate_audit_sync import (
    validate_change_sync,
    validate_structure,
)

SAMPLE_VALID_AUDIT: str = """# Codebase Audit Report: finances-manager

## 1. Missing Local Files & Environment Setup
- [x] **Sample Item**:
  - Details.
- [ ] **Open Item**:
  - Details.

## 2. Bugs & Code Fragilities
- [x] **Sample Bug**:
  - Details.

## 3. Test Coverage Gaps
- [x] **Sample Coverage**:
  - Details.
"""


def test_validate_structure_missing_file(tmp_path: Path) -> None:
    non_existent: Path = tmp_path / "NON_EXISTENT.md"
    is_valid, completed, opened = validate_structure(non_existent)
    assert is_valid is False
    assert completed == 0
    assert opened == 0


def test_validate_structure_valid_content(tmp_path: Path) -> None:
    audit_file: Path = tmp_path / "AUDIT.md"
    audit_file.write_text(SAMPLE_VALID_AUDIT, encoding="utf-8")
    is_valid, completed, opened = validate_structure(audit_file)
    assert is_valid is True
    assert completed == 3
    assert opened == 1


def test_validate_change_sync_bypass() -> None:
    assert validate_change_sync(bypass=True) is True
