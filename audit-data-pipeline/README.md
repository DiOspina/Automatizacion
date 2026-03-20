# Audit Data Pipeline

Robot en Python que automatiza la **obtención, preparación y validación** de
datos transaccionales para auditoría interna, replicando el día a día de un
*Automation Engineer Jr.* del área de Analítica e Inteligencia Artificial de
Auditoría Interna.

Simula la salida de un ERP (estilo **SAP**: tablas `BKPF`, `BSEG`, `EKPO`)
mediante archivos de **formatos heterogéneos** y concilia los datos contra
**totales de control** declarados por el sistema de origen.

---

## ¿Qué hace el robot?

```
Entrada (heterogénea)          Procesamiento                      Salida
┌────────────────────┐   ┌──────────────────────────────────┐   ┌───────────────────┐
│ BKPF.csv   (CSV)   │──▶│ 1. Ingesta y normalización        │──▶│ Reporte de        │
│ BSEG.txt   (pipe)  │   │ 2. Validación (integridad/compl)  │   │ evidencia:        │
│ EKPO.dat   (tab)   │   │ 3. Procedimientos de auditoría    │   │  Markdown + HTML  │
│ control_totals.csv │   │ 4. Logging + errores + reintentos │   └───────────────────┘
└────────────────────┘   └──────────────────────────────────┘
```

### Etapa 1 — Ingesta y normalización (`src/pipeline/ingest.py`)
- Lee archivos de distintos formatos (`csv`, `pipe`, `tab`, `xlsx`, `json`)
  desde una **especificación declarativa** (`SOURCE` en `config.py`).
- Normaliza tipos de negocio (montos numéricos, campos de texto, fechas).
- **Reintentos** (retries) ante fallos transitorios de lectura.

### Etapa 2 — Validaciones (`src/pipeline/validate.py`)
- **Conciliación contra totales de control**: la suma de líneas y montos debe
  cuadrar (con tolerancia) contra lo que declara el sistema.
- **Completitud**: sin nulos en campos críticos.
- **Sin duplicados** exactos.
- **Integridad monetaria**: montos no negativos.

### Etapa 3 — Procedimientos de auditoría (`src/pipeline/audit.py`)
- **Segregación de funciones (SoD)**: detecta proveedores que aparecen a la vez
  en compras (`EKPO`) y en pagos (`BSEG`).
- **Anomalías por umbral**: montos por encima de un límite de aprobación.
- **Coherencia referencial**: líneas cuyo documento no existe en la cabecera.

### Etapa 4 — Reporte de evidencia (`src/pipeline/report.py`)
- Genera un informe Markdown + HTML ("la evidencia ante el cliente") con las
  tablas de validaciones y los hallazgos por severidad.

---

## Cómo ejecutarlo

```bash
# 1) Entorno
python -m venv .venv
.venv\Scripts\activate          # Windows        (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 2) Generar (o regenerar) los datos sintéticos de ejemplo
python src/generate_data.py

# 3) Correr el robot
python src/main.py
```

El reporte se escribe en `data/output/reporte_auditoria_<fecha>.{md,html}` y los
logs en `data/output/logs/`.

Para ejecución **desatendida / calendarizada**, invocar `main.py` desde cron,
el Planificador de tareas de Windows o Airflow (ver sección de extensión).

---

## Estructura del proyecto

```
audit-data-pipeline/
├─ data/
│  ├─ raw/        # datos "extraídos del ERP" (heterogéneos)
│  ├─ control/    # totales de control
│  └─ output/     # reportes + logs
├─ src/
│  ├─ generate_data.py      # generador de datos sintéticos
│  ├─ main.py               # orquestador (cron-friendly)
│  └─ pipeline/
│     ├─ config.py          # rutas, fuentes, logging
│     ├─ ingest.py          # etapa 1
│     ├─ validate.py        # etapa 2
│     ├─ audit.py           # etapa 3
│     └─ report.py          # etapa 4
└─ tests/                   # pruebas unitarias
```

---

## Conceptos de auditoría que demuestra

| Concepto (referencia) | Dónde |
|---|---|
| Tablas SAP contabilidad (`BKPF`/`BSEG`) | datos de ejemplo + `audit.py` |
| Tablas SAP compras/CXP (`EKKO`/`EKPO` equivalentes) | datos de ejemplo + `audit.py` |
| Totales de control y conciliación | `validate.py` |
| Integridad / completitud de datos | `validate.py` |
| Segregación de funciones (SoD) | `audit.py` |
| Detección de duplicados y anomalías | `validate.py` + `audit.py` |
| Evidencia sustentable ante el cliente | `report.py` |
| Manejo de errores, reintentos y logging | `ingest.py` + `config.py` |

---

## Ideas de extensión (para "subirlo de nivel" en el portafolio)

- **Orquestación con Airflow / cron**: añade un `DAG` que ejecute `main()` a
  diario por cliente.
- **Empaquetado Docker**: un `Dockerfile` que ejecute el pipeline (cierra el
  "entorno productivo" que menciona el puesto).
- **Conexión real a ERP**: sustituir la lectura de archivos por conectores
  (OData / RFC-BAPI para SAP, o un conector a una BD Postgres/SQL Server).
- **Dashboard en Power BI**: consumir los reportes salientes para monitoreo
  continuo.
- **Más pruebas de auditoría**: muestreo estadístico (MUS), Benford, retrabajo
  de conciliaciones.

---

## Nota de diseño

Los *totales de control* se calculan sobre el archivo **final** extraído para
que la conciliación cuadre y el repunte de **hallazgos** (SoD, umbral, nulos,
duplicados) sea detectado por los *procedimientos de auditoría*, no por un
defecto de extracción. Cambia la `seed` en `generate_data.py` para obtener
datos distintos en cada ejecución.