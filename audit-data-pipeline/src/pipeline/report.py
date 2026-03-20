"""Etapa 4 — Generación del reporte de evidencia.

El puesto pide "sustentar la evidencia ante el cliente": transforma los
resultados de validaciones y los hallazgos en un documento Markdown (y HTML)
listo para adjuntar o publicar.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, get_logger

logger = get_logger("report")


def _timedelta_human(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def build_markdown(
    *,
    sources: dict[str, pd.DataFrame],
    validations: list,
    findings: list,
    timing: float,
) -> str:
    """Construye el reporte de evidencia en Markdown."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# Reporte de Auditoría — Datos Transaccionales")
    lines.append("")
    lines.append(f"**Fecha de ejecución:** {now}")
    lines.append(f"**Duración de la corrida:** {_timedelta_human(timing)}")
    lines.append("")

    # 1) Datos procesados
    lines.append("## 1. Datos procesados")
    lines.append("")
    lines.append("| Fuente | Filas | Columnas |")
    lines.append("|--------|------:|--------:|")
    for name, df in sources.items():
        lines.append(f"| {name} | {len(df)} | {df.shape[1]} |")
    lines.append("")

    # 2) Validaciones de datos
    lines.append("## 2. Validaciones de datos")
    lines.append("")
    lines.append("| Prueba | Estado | Detalle |")
    lines.append("|--------|--------|---------|")
    for v in validations:
        icon = {"PASS": "", "WARN": "", "FAIL": ""}.get(v.status, v.status)
        lines.append(f"| {v.name} | {icon} {v.status} | {v.details} |")
        for issue in v.issues:
            lines.append(f"  - `{issue}`")
    lines.append("")

    # 3) Procedimientos de auditoría
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        counts[f.severity] += 1
    lines.append("## 3. Procedimientos de auditoría")
    lines.append("")
    lines.append(f"Hallazgos por severidad: **{counts['HIGH']} alto**, **{counts['MEDIUM']} medio**, **{counts['LOW']} bajo**.")
    lines.append("")
    for f in findings:
        lines.append(f"### {f.severity} — {f.procedure}")
        lines.append("")
        lines.append(f"{f.description}")
        if f.references:
            lines.append("")
            lines.append("Referencias:")
            for r in f.references[:8]:
                lines.append(f"- `{r}`")
        lines.append("")

    # 4) Conclusión
    n_fail = sum(1 for v in validations if v.status == "FAIL")
    lines.append("## 4. Conclusión")
    lines.append("")
    if n_fail:
        lines.append(f"Se detectaron **{n_fail} validaciones FALLIDA(s)** y "
                     f"**{counts['HIGH'] + counts['MEDIUM']} hallazgo(s)** de severidad media/alta. "
                     "Se recomienda revisión y extracción corregida antes de emitir evidencia.")
    else:
        lines.append("No se detectaron incumplimientos críticos de integridad. "
                     "Documento cuadra contra los totales de control.")
    lines.append("")
    lines.append("---")
    lines.append("*Generado automáticamente por el robot `audit_data_pipeline`.*")
    return "\n".join(lines)


def render_html(md: str) -> str:
    """Paso extremadamente ligero: enmarca el markdown en HTML simple."""
    body = html.escape(md).replace("\n", "<br>")
    return f"<!doctype html><html><body><pre>{body}</pre></body></html>"


def write_reports(md: str) -> tuple[Path, Path]:
    """Guarda el Markdown y HTML en data/output con la fecha en el nombre."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = OUTPUT_DIR / f"reporte_auditoria_{stamp}.md"
    html_path = OUTPUT_DIR / f"reporte_auditoria_{stamp}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    logger.info("Reportes generados: %s y %s", md_path.name, html_path.name)
    return md_path, html_path