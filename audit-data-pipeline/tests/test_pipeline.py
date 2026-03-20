"""Pruebas unitarias mínimas del pipeline.

Ejecutar desde la raíz del proyecto (donde está `src/`):

    python -m pytest -q
    # o sin pytest
    python tests/test_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline import config  # noqa: E402
from pipeline.audit import sod_sobre_proveedores  # noqa: E402
from pipeline.ingest import ingest_source, normalize_source  # noqa: E402
from pipeline.validate import (  # noqa: E402
    validate_amounts_positive,
    validate_completeness,
    validate_no_duplicates,
    validate_totals_against_control,
)


def test_all_sources_ingest():
    for name in ("BKPF", "BSEG", "EKPO"):
        df = ingest_source(config.SOURCES[name])
        assert not df.empty, f"{name} no debería estar vacío"
        df = normalize_source(df, config.SOURCES[name])
        assert len(df) > 0


def test_control_has_expected_concepts():
    ctrl = pd.read_csv(config.CONTROL_FILE)
    concepts = set(ctrl["concept"].str.strip())
    assert {"total_lines", "total_amount", "unique_documents"} <= concepts


def test_completeness_flags_nulls():
    bseg = normalize_source(
        ingest_source(config.SOURCES["BSEG"]), config.SOURCES["BSEG"]
    )
    result = validate_completeness(bseg)
    assert result.name == "completitud_datos"
    assert any("WRBTR" in i for i in result.issues)  # los nulos inyectados


def test_duplicates_flags():
    bseg = normalize_source(
        ingest_source(config.SOURCES["BSEG"]), config.SOURCES["BSEG"]
    )
    result = validate_no_duplicates(bseg)
    assert result.issues  # duplicados inyectados


def test_soD_detects_overlap():
    ekpo = normalize_source(
        ingest_source(config.SOURCES["EKPO"]), config.SOURCES["EKPO"]
    )
    bseg = normalize_source(
        ingest_source(config.SOURCES["BSEG"]), config.SOURCES["BSEG"]
    )
    finding = sod_sobre_proveedores(ekpo, bseg)
    assert "L123456" in finding.references


def _run_tests() -> None:
    tests = [
        test_all_sources_ingest,
        test_control_has_expected_concepts,
        test_completeness_flags_nulls,
        test_duplicates_flags,
        test_soD_detects_overlap,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(f"{failed} prueba(s) fallaron")
    print("Todas las pruebas pasaron.")


if __name__ == "__main__":
    _run_tests()