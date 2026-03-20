"""Etapa 2 — Validaciones de integridad, completitud y conciliación.

Estas son las validaciones que le pedirían a un Automation Engineer en
Auditoría Interna: que los datos extraídos sean íntegros, completos y que
cuadren contra los totales de control declarados por el sistema de origen.

Cada validación devuelve un objeto ValidationResult que la etapa de reporte
convertirá en evidencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import AMOUNT_TOLERANCE_PCT, get_logger

logger = get_logger("validate")


@dataclass
class ValidationResult:
    """Resultado de una validación (una 'prueba' de auditoría)."""

    name: str
    status: str  # 'PASS' | 'FAIL' | 'WARN'
    details: str = ""
    issues: list[str] = field(default_factory=list)


def _r(ok: bool, warn_only: bool) -> str:
    return "PASS" if ok else ("WARN" if warn_only else "FAIL")


def validate_totals_against_control(
    bseg: pd.DataFrame, control: pd.DataFrame
) -> ValidationResult:
    """Conciliación de la suma de líneas contra los totales de control.

    Conceptos esperados en control_totals.csv:
        total_lines    -> número de líneas (WRBTR no nulo)
        total_amount   -> suma de WRBTR
        unique_documents -> BELNR únicos
    """
    issues: list[str] = []
    ok = True

    for _, row in control.iterrows():
        concept, expected = str(row["concept"]).strip(), row["value"]
        if concept == "total_lines":
            actual = int(bseg["WRBTR"].notna().sum())
        elif concept == "total_amount":
            actual = float(bseg["WRBTR"].fillna(0).sum())
        elif concept == "unique_documents":
            actual = int(bseg["BELNR"].nunique())
        else:
            continue

        if concept == "total_amount":
            # tolerancia relativa para no fallar por redondeo de centavos
            diff_pct = abs(actual - expected) / expected * 100 if expected else 0.0
            match = diff_pct <= AMOUNT_TOLERANCE_PCT
            detail = f"total_amount esperado={expected} vs extraído={actual:.2f} (Δ {diff_pct:.4f}%)"
        else:
            match = actual == expected
            detail = f"{concept}: esperado={expected} vs extraído={actual}"

        if match:
            logger.info("Conciliación OK  -> %s", detail)
        else:
            ok = False
            issues.append(f"NO CUADRA -> {detail}")
            logger.warning("Conciliación FALLÓ -> %s", detail)

    return ValidationResult(
        name="conciliacion_totales",
        status=_r(ok, warn_only=False),
        details=f"Conciliación de BSEG contra {len(control)} controles",
        issues=issues,
    )


def validate_completeness(bseg: pd.DataFrame) -> ValidationResult:
    """Completitud: no debe haber nulos en campos críticos de negocio."""
    critical = ["BELNR", "BUZEI", "SHKZG", "WRBTR", "BSCHL", "HKONT"]
    issues: list[str] = []
    for col in critical:
        if col in bseg.columns:
            nnull = int(bseg[col].isna().sum())
            if nnull:
                issues.append(f"{col}: {nnull} valores nulos/faltantes")

    ok = not issues
    if ok:
        logger.info("Completitud OK: sin nulos en campos críticos")
    else:
        logger.warning("Completitud INCOMPLETA: %s", "; ".join(issues))

    return ValidationResult(
        name="completitud_datos",
        status=_r(ok, warn_only=False),
        details="Campos críticos de BSEG sin valores faltantes",
        issues=issues,
    )


def validate_no_duplicates(bseg: pd.DataFrame) -> ValidationResult:
    """Detección de duplicados exactos en las líneas de documento."""
    if bseg.empty:
        return ValidationResult("sin_duplicados", "PASS", "Sin datos que revisar")
    dup = bseg[bseg.duplicated(keep="first")]
    issues = []
    if not dup.empty:
        sample = dup.head(3)[["BELNR", "BUZEI", "WRBTR"]].to_string(index=False)
        issues.append(f"{len(dup)} filas duplicadas exactas. Muestra:\n{sample}")
        logger.warning("Duplicados detectados: %d", len(dup))
    else:
        logger.info("Sin duplicados exactos")

    return ValidationResult(
        name="sin_duplicados",
        status=_r(dup.empty, warn_only=False),
        details=f"Revisión de {len(bseg)} filas por duplicados exactos",
        issues=issues,
    )


def validate_amounts_positive(bseg: pd.DataFrame) -> ValidationResult:
    """Integridad monetaria: WRBTR nunca debe ser negativo (tras el signo SHKZG)."""
    if "WRBTR" not in bseg.columns:
        return ValidationResult("montos_no_negativos", "WARN", "Sin columna WRBTR")
    neg = bseg[bseg["WRBTR"] < 0]
    issues = []
    if not neg.empty:
        issues.append(f"{len(neg)} filas con WRBTR negativo")
        logger.warning("Montos negativos inesperados: %d", len(neg))
    return ValidationResult(
        name="montos_no_negativos",
        status=_r(neg.empty, warn_only=True),  # warn, no fatal
        details="WRBTR (valor absoluto) no debe ser negativo",
        issues=issues,
    )


def run_all(bseg: pd.DataFrame, control: pd.DataFrame) -> list[ValidationResult]:
    """Ejecuta todas las validaciones y devuelve sus resultados."""
    return [
        validate_totals_against_control(bseg, control),
        validate_completeness(bseg),
        validate_no_duplicates(bseg),
        validate_amounts_positive(bseg),
    ]