"""Etapa 1 — Ingesta y normalización.

Simula que el robot descarga/lee archivos de distinto formato y los convierte
a un DataFrame limpio y normalizado listo para validar.

Incluye reintentos (retries) ante fallos transitorios de lectura, tal como se
espera en una ejecución desatendida.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from .config import Source, get_logger, resolve_file

logger = get_logger("ingest")


class UnsupportedFormatError(Exception):
    """El archivo no tiene una extensión soportada."""


def _read_file(path: Path, source: Source) -> pd.DataFrame:
    """Lee un archivo según su extensión."""
    ext = path.suffix.lower()
    kwargs: dict = {}

    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".json":
        return pd.read_json(path, orient="records")
    if ext in (".csv", ".txt", ".dat", ".tsv", ".log"):
        return pd.read_csv(
            path,
            sep=source.sep or ",",
            encoding=source.encoding,
            dtype=source.dtype,
            parse_dates=source.parse_dates,
            na_values=["", "NULL", "null", "NaN", "#N/A"],
        )

    raise UnsupportedFormatError(f"Extensión no soportada: {ext}")


def ingest_source(source: Source, max_retries: int = 3, retry_wait: float = 0.5) -> pd.DataFrame:
    """Lee una fuente con reintentos ante errores transitorios."""
    path = resolve_file(source)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            df = _read_file(path, source)
            logger.info("Leído %-5s: %6d filas de %s (intento %d)", source.name, len(df), path.name, attempt)
            return df
        except Exception as exc:  # noqa: BLE001 — reintentamos cualquier fallo
            last_error = exc
            logger.warning("Error al leer %s (intento %d/%d): %s", source.name, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_wait)

    raise RuntimeError(f"No fue posible leer '{source.name}' tras {max_retries} intentos: {last_error}") from last_error


def check_required(df: pd.DataFrame, source: Source) -> None:
    """Verifica que las columnas obligatorias existan."""
    missing = [c for c in source.required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"'{source.name}': faltan columnas requeridas {missing}. Presentes: {list(df.columns)}"
        )
    logger.debug("Columna requeridas de %s presentes", source.name)


def normalize_source(df: pd.DataFrame, source: Source) -> pd.DataFrame:
    """Deja la fuente lista para las etapas siguientes."""
    out = df.copy()

    # Columnas en mayúsculas y espacios recortados por seguridad
    out.columns = [str(c).strip().upper() for c in out.columns]

    # Coerciones de tipo por convención de negocio
    for col in (
        "BELNR",
        "BUZEI",
        "EBELN",
        "EBELP",
        "LIFNR",
        "KUNNR",
        "MATNR",
        "BUKRS",
    ):
        if col in out.columns:
            out[col] = out[col].astype("string").str.strip()

    for col in ("WRBTR", "NETWR", "MENGE"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    logger.info("%-5s normalizado: %d filas, %d columnas", source.name, len(out), out.shape[1])
    return out