"""Genera datos sintéticos que simulan la salida de un ERP (estilo SAP).

Crea tres fuentes "heterogéneas" de datos transaccionales + un archivo
de totales de control (control totals), tal como los vería un robot que
extrae información de SAP u Oracle para una auditoría.

Los archivos imitan tablas SAP:
    - BKPF  : cabeceras de documento contable (HDR)
    - BSEG  : posiciones / líneas de documento (ITEM)
    - EKPO  : posiciones de órdenes de compra (PO_ITEM)
Los "totales de control" son lo que el sistema de origen reporta y contra
lo cual el robot debe conciliar la suma de las líneas extraídas.

De forma intencional se inyectan errores (filas incompletas, montos que no
cuadran, duplicados) para que las validaciones tengan algo que detectar.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CTRL_DIR = ROOT / "data" / "control"

random.seed(42)


def _as_of_dates(n_days: int = 30) -> list[date]:
    """Últimos n_days hábiles aproximados (lunes a viernes)."""
    days: list[date] = []
    today = date.today()
    cur = today
    while len(days) < n_days:
        if cur.weekday() < 5:
            days.append(cur)
        cur -= timedelta(days=1)
    return sorted(days)


def build_bkpf(dates: list[date]) -> pd.DataFrame:
    """Cabeceras de documentos contables (SAP BKPF)."""
    rows = []
    for i, d in enumerate(dates, start=1):
        # 1 documento de ventas + 1 de compras al día
        rows.append(
            {
                "BELNR": f"009{d:08d}0{i}0",
                "BUKRS": "1000",
                "GJAHR": d.year,
                "BLDAT": d.strftime("%Y-%m-%d"),
                "BUDAT": (d - timedelta(days=1)).strftime("%Y-%m-%d"),
                "WAERS": "MXN",
                "KTOPL": "S07",
            }
        )
        rows.append(
            {
                "BELNR": f"009{d:08d}0{i}1",
                "BUKRS": "1000",
                "GJAHR": d.year,
                "BLDAT": d.strftime("%Y-%m-%d"),
                "BUDAT": d.strftime("%Y-%m-%d"),
                "WAERS": "MXN",
                "KTOPL": "S07",
            }
        )
    return pd.DataFrame(rows)


def build_bseg(bkpf: pd.DataFrame, n_items: int = 3) -> pd.DataFrame:
    """Líneas de documentos contables (SAP BSEG), una fila = una línea.

    Cada documento tiene entre 1 y n_items líneas. El total por documento
    se reparte en montos positivos/negativos. Se inyectan errores:
        - algunas líneas con monto nulo (incompletitud de datos)
        - un par de duplicados exactos
    """
    rows: list[dict] = []
    for _, hdr in bkpf.iterrows():
        k = random.randint(1, n_items)
        base = round(random.uniform(1000, 9000), 2)
        parts = [base] + [round(random.uniform(-600, 600), 2) for _ in range(k - 1)]
        # Ajustar la primera línea para que la suma del documento cuadre
        parts[0] = round(base - sum(parts[1:]), 2) if len(parts) > 1 else base
        for j, amt in enumerate(parts, start=1):
            rows.append(
                {
                    "BELNR": hdr["BELNR"],
                    "BUZEI": j,
                    "SHKZG": "S" if amt >= 0 else "H",
                    "WRBTR": float(abs(round(amt, 2))),
                    "BSCHL": random.choice(["40", "50", "31", "21"]),
                    "HKONT": random.choice(
                        ["51000000", "51100000", "12000000", "20100000"]
                    ),
                    "LIFNR": f"L{random.randint(100000, 999999)}",
                    "KUNNR": f"K{random.randint(100000, 999999)}",
                }
            )

    df = pd.DataFrame(rows)

    # --- inyectar errores ---
    # 4 líneas con WRBTR nulo (campo faltante / incompletitud)
    for idx in random.sample(list(df.index), min(4, len(df))):
        df.loc[idx, "WRBTR"] = None
    # 2 duplicados exactos (de una fila completa, sin nulos)
    src = df.dropna().sample(1, replace=False)
    df = pd.concat([df, src], ignore_index=True)
    df = pd.concat([df, src], ignore_index=True)

    return df.reset_index(drop=True)


def build_ekpo() -> pd.DataFrame:
    """Posiciones de órdenes de compra (SAP EKPO), archivo separado."""
    rows = []
    for i in range(120):
        rows.append(
            {
                "EBELN": f"45{i:07d}",
                "EBELP": i % 10,
                "MATNR": f"M{i:08d}",
                "LIFNR": f"L{random.randint(100000, 999999)}",
                "MENGE": round(random.uniform(1, 500), 2),
                "NETWR": round(random.uniform(100, 50000), 2),
                "WAERS": "MXN",
            }
        )
    # un proveedor repetido de forma inesperada (para SoD)
    rows.append(
        {
            "EBELN": "45",
            "EBELP": 0,
            "MATNR": "M00000001",
            "LIFNR": "L123456",
            "MENGE": 99.0,
            "NETWR": 99999.99,
            "WAERS": "MXN",
        }
    )
    return pd.DataFrame(rows)


def build_control(bkpf: pd.DataFrame, bseg: pd.DataFrame) -> pd.DataFrame:
    """Totales de control: lo que el sistema de origen declara.

    Se calculan a partir de los datos *antes* de inyectar errores en BSEG
    para que, al no cuadrar con lo extraído, la conciliación lo detecte.
    """
    total_lines_ok = int(bseg["WRBTR"].notna().sum())
    total_amount = float(bseg["WRBTR"].fillna(0).sum())
    return pd.DataFrame(
        [
            {"concept": "total_lines", "value": total_lines_ok},
            {"concept": "total_amount", "value": round(total_amount, 2)},
            {"concept": "unique_documents", "value": int(bkpf["BELNR"].nunique())},
        ]
    )


def write_heterogeneous(raw: pd.DataFrame, name: str, fmt: str) -> Path:
    """Escribe un DataFrame en un formato distinto a propósito."""
    out = RAW_DIR / name
    if fmt == "csv":
        raw.to_csv(out, index=False)
    elif fmt == "csv_pipe":
        raw.to_csv(out, sep="|", index=False)
    elif fmt == "tsv":
        raw.to_csv(out, sep="\t", index=False)
    elif fmt == "excel":
        raw.to_excel(out.with_suffix(".xlsx"), index=False)
    elif fmt == "json":
        raw.to_json(out.with_suffix(".json"), orient="records")
    return out


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CTRL_DIR.mkdir(parents=True, exist_ok=True)

    dates = _as_of_dates()
    bkpf = build_bkpf(dates)
    bseg = build_bseg(bkpf)
    ekpo = build_ekpo()

    # --- hallazgos controlados para que el robot los *detecte* ---
    # 1) Proveedor que aparece en compras (EKPO) Y en pagos (BSEG) -> SoD
    bseg.loc[bseg.index[:6], "LIFNR"] = "L123456"
    # 2) Un monto por encima del umbral de aprobación -> anomalía
    bseg.loc[bseg.index[7], "WRBTR"] = 50000.0

    # Los totales de control se calculan sobre el archivo FINAL extraído,
    # de modo que la conciliación cuadre y los hallazgos los destaque el
    # procedimiento de auditoría (no un defecto de extracción).
    ctrl = build_control(bkpf, bseg)
    CTRL_DIR.joinpath("control_totals.csv").write_text(
        ctrl.to_csv(index=False), encoding="utf-8"
    )

    # Archivos de intencionalmente heterogéneos
    write_heterogeneous(bkpf, "BKPF.csv", "csv")
    write_heterogeneous(bseg, "BSEG.txt", "csv_pipe")  # separado por pipe
    write_heterogeneous(ekpo, "EKPO.dat", "tsv")  # separado por tab

    print(f"BKPF: {len(bkpf)} filas   BSEG: {len(bseg)} filas   EKPO: {len(ekpo)} filas")
    print("Archivos de control generados.")


if __name__ == "__main__":
    main()