"""Configuración central del pipeline.

Define rutas de entrada/salida y la especificación de cada fuente de datos
heterogénea. Esto permite que el pipeline se adapte a nuevos formatos sin
tocar la lógica de negocio: basta con añadir una entrada a SOURCES.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CTRL_DIR = DATA_DIR / "control"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = OUTPUT_DIR / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Umbral de tolerancia para la conciliación de montos (porcentaje)
AMOUNT_TOLERANCE_PCT = 0.01


@dataclass
class Source:
    """Define cómo leer una tabla ERP de formato heterogéneo."""

    name: str  # Nombre lógico (p. ej. 'BKPF')
    file_name: str  # Nombre del archivo en RAW_DIR (se resuelve p. ej. .xlsx)
    sep: str | None = ","  # Separador (None para excel/json)
    encoding: str = "utf-8"
    dtype: dict = field(default_factory=dict)
    parse_dates: list[str] = field(default_factory=list)
    required_cols: list[str] = field(default_factory=list)


# Fuentes soportadas por el robot. "fmt" se resuelve buscando el archivo.
SOURCES: dict[str, Source] = {
    "BKPF": Source(
        name="BKPF",
        file_name="BKPF",
        dtype={"BELNR": str, "BUKRS": str},
        parse_dates=["BLDAT", "BUDAT"],
        required_cols=["BELNR", "BUKRS", "GJAHR", "BLDAT", "WAERS"],
    ),
    "BSEG": Source(
        name="BSEG",
        file_name="BSEG",
        sep="|",
        dtype={"BELNR": str, "BUZEI": str},
        required_cols=["BELNR", "BUZEI", "SHKZG", "WRBTR"],
    ),
    "EKPO": Source(
        name="EKPO",
        file_name="EKPO",
        sep="\t",
        dtype={"EBELN": str, "EBELP": str},
        required_cols=["EBELN", "EBELP", "LIFNR", "NETWR"],
    ),
}

# Totales de control
CONTROL_FILE = CTRL_DIR / "control_totals.csv"


def resolve_file(source: Source) -> Path:
    """Devuelve la ruta del archivo real entre las extensiones soportadas."""
    for ext in (".csv", ".txt", ".dat", ".tsv", ".xlsx", ".json"):
        candidate = RAW_DIR / (source.file_name + ext)
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No se encontró el archivo '{source.file_name}' en {RAW_DIR}")


# ---------------------------------------------------------------------------
# Logging compartido
# ---------------------------------------------------------------------------
def get_logger(name: str = "audit_pipeline") -> logging.Logger:
    """Devuelve un logger que escribe en consola y en un archivo de rotación."""
    logger = logging.getLogger(name)
    if logger.handlers:  # ya configurado
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger