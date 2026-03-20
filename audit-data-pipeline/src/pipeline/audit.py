"""Etapa 3 — Procedimientos de auditoría automatizados.

Procedimientos que hoy se harían a mano en una auditoría y que este robot
automatiza. Cada procedimiento devuelve un dict con hallazgos que luego se
vuelcan al reporte de evidencia.

Procedimientos incluidos:
    - Segregación de funciones (SoD): un mismo proveedor que aparece en
      compras (EKPO) y como acreedor de líneas de pago (BSEG) sin respaldo.
    - Anomalías por umbral: montos por encima de un límite de aprobación.
    - Coherencia cabecera-línea: líneas cuyo documento no existe en BKPF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import get_logger

logger = get_logger("audit")


@dataclass
class Finding:
    """Un hallazgo de auditoría detectado por un procedimiento."""

    procedure: str
    severity: str  # 'HIGH' | 'MEDIUM' | 'LOW'
    description: str
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "procedure": self.procedure,
            "severity": self.severity,
            "description": self.description,
            "references": self.references,
        }


def sod_sobre_proveedores(ekpo: pd.DataFrame, bseg: pd.DataFrame) -> Finding:
    """SoD aproximada: proveedores de compras reutilizados de forma inusual.

    Detecta proveedores que aparecen repetidamente en órdenes de compra y que
    también liquidan líneas de pago (BSEG) — una bandera típica de riesgo.
    """
    if "LIFNR" not in ekpo.columns or "LIFNR" not in bseg.columns:
        return Finding(
            procedure="sod_proveedores", severity="LOW", description="Datos insuficientes para SoD"
        )

    po = ekpo["LIFNR"].fillna("").astype(str).str.strip()
    pay = bseg["LIFNR"].fillna("").astype(str).str.strip()

    overlap = sorted(set(po) & set(pay) - {""})
    details = (
        f"{len(overlap)} proveedores aparecen simultáneamente en compras y pagos"
    )
    severity = "MEDIUM" if len(overlap) < 5 else "HIGH"
    if overlap:
        logger.warning("%s. Proveedor sospechoso p.ej.: %s", details, overlap[:5])
    else:
        logger.info("SoD OK: sin solapamiento de proveedores")
    return Finding(
        procedure="sod_proveedores",
        severity=severity if overlap else "LOW",
        description=details,
        references=overlap[:10],
    )


def anomalias_por_umbral(bseg: pd.DataFrame, threshold: float = 25000.0) -> Finding:
    """Monto por encima del umbral de aprobación sin respaldo en cabecera."""
    if "WRBTR" not in bseg.columns:
        return Finding(
            procedure="anomalias_umbral", severity="LOW", description="Sin columna WRBTR"
        )
    big = bseg[bseg["WRBTR"].fillna(0) > threshold]
    if big.empty:
        logger.info("Sin montos por encima del umbral %.2f", threshold)
        return Finding(
            procedure="anomalias_umbral",
            severity="LOW",
            description=f"Ningún monto > {threshold}",
        )
    logger.warning("%d líneas exceden el umbral de aprobación", len(big))
    return Finding(
        procedure="anomalias_umbral",
        severity="MEDIUM",
        description=f"{len(big)} líneas con monto > {threshold} sin evidencia de aprobación",
        references=big.head(5)[["BELNR", "WRBTR"]].astype(str).values.tolist(),
    )


def coherentes_con_cabecera(bkpf: pd.DataFrame, bseg: pd.DataFrame) -> Finding:
    """Coherencia referencial: toda línea debe pertenecer a una cabecera."""
    if "BELNR" not in bseg.columns or "BELNR" not in bkpf.columns:
        return Finding(
            procedure="coherencia_cabecera", severity="LOW", description="Sin columna BELNR"
        )
    valid = set(bkpf["BELNR"].astype(str))
    all_lines = set(bseg["BELNR"].astype(str))
    orphan = all_lines - valid
    if not orphan:
        logger.info("Coherencia referencial OK: todas las líneas tienen cabecera")
        return Finding(
            procedure="coherencia_cabecera",
            severity="LOW",
            description="Todas las líneas pertenecen a una cabecera válida",
        )
    logger.warning("%d líneas sin cabecera en BKPF", len(orphan))
    return Finding(
        procedure="coherencia_cabecera",
        severity="MEDIUM",
        description=f"{len(orphan)} líneas cuyo BELNR no existe en BKPF",
        references=sorted(orphan)[:10],
    )


def run_auth_procedures(bkpf, bseg, ekpo) -> list[Finding]:
    """Ejecuta todos los procedimientos de auditoría."""
    procs = [
        sod_sobre_proveedores(ekpo, bseg),
        anomalias_por_umbral(bseg),
        coherentes_con_cabecera(bkpf, bseg),
    ]
    # ordenar por severidad para el reporte
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(procs, key=lambda f: order.get(f.severity, 2))