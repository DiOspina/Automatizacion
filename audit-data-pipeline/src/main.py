"""Orquestador principal del robot de auditoría.

Encadena las etapas del pipeline y garantiza una ejecución desatendida con
logging y manejo de errores:
    1. Ingestar y normalizar las fuentes heterogéneas (BKPF, BSEG, EKPO).
    2. Validar integridad, completitud y conciliación contra totales.
    3. Ejecutar procedimientos de auditoría (SoD, umbrales, coherente).
    4. Generar reporte de evidencia (Markdown + HTML).

Es "cron-friendly": se puede invocar con Python una vez al día.
"""

from __future__ import annotations

import time

from pipeline.audit import run_auth_procedures
from pipeline.config import CONTROL_FILE, SOURCES, get_logger
from pipeline.ingest import check_required, ingest_source, normalize_source
from pipeline.report import build_markdown, write_reports
from pipeline.validate import run_all

logger = get_logger("main")


def _read_control(path) -> "list":
    import pandas as pd

    df = pd.read_csv(path, skip_blank_lines=True)
    # normalizar nombres de columna a minúsculas y quitar espacios
    df.columns = [str(c).strip().lower() for c in df.columns]
    # el valor de los totales numéricos debe interpretarse como número
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["concept"])


def main() -> int:
    started = time.perf_counter()
    logger.info("========== INICIO de ejecución del robot ==========")

    # --- 1. Ingesta ---
    sources: dict = {}
    try:
        for name in ("BKPF", "BSEG", "EKPO"):
            src = SOURCES[name]
            raw = ingest_source(src)
            raw = normalize_source(raw, src)
            check_required(raw, src)
            sources[name] = raw
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falla en etapa de ingesta: %s", exc)
        raise SystemExit(1) from exc

    # --- 2. Validaciones ---
    control = _read_control(CONTROL_FILE)
    logger.info("Controles leídos: %d", len(control))
    validations = run_all(sources["BSEG"], control)

    # --- 3. Procedimientos de auditoría ---
    findings = run_auth_procedures(
        sources["BKPF"], sources["BSEG"], sources["EKPO"]
    )

    # --- 4. Reporte ---
    elapsed = time.perf_counter() - started
    md = build_markdown(
        sources=sources,
        validations=validations,
        findings=findings,
        timing=elapsed,
    )
    write_reports(md)

    logger.info("========== FIN de ejecución (%s) ==========", f"{elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())