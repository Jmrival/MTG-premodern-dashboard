# MTG Premodern Analytics

Proyecto de data science sobre el metagame de **Magic: The Gathering — formato Premodern**,
basado en resultados de torneos publicados en [tcdecks.net](https://www.tcdecks.net).

Incluye scraping de torneos/mazos/cartas, análisis de metagame con Python/SQL y un
dashboard interactivo en Streamlit.

---

## Compatibilidad

Funciona en **Windows, macOS y Linux** sin cambios. Todas las rutas de archivo usan
la librería estándar `pathlib`, que se adapta automáticamente al sistema operativo.

---

## Requisitos previos

Antes de empezar necesitás tener instalado:

### 1. Python 3.11 o superior

Verificá si ya lo tenés abriendo una terminal y escribiendo:

```
python --version
```

Si no tenés Python o la versión es anterior a 3.11:
- **Windows/macOS**: descargá el instalador desde [python.org/downloads](https://www.python.org/downloads/)
  - En Windows, durante la instalación marcá la opción **"Add Python to PATH"** (importante)
- **Linux (Ubuntu/Debian)**: `sudo apt install python3.11 python3.11-venv python3-pip`

### 2. Git (opcional, para clonar el repositorio)

- **Windows**: [git-scm.com/download/win](https://git-scm.com/download/win)
- **macOS**: viene preinstalado, o instalá con `brew install git`
- **Linux**: `sudo apt install git`

---

## Instalación paso a paso

### Paso 1 — Obtener el código

**Opción A — con Git (recomendado):**

Abrí una terminal (en Windows: buscá "Símbolo del sistema" o "PowerShell" en el menú inicio),
navegá a la carpeta donde querés guardar el proyecto y ejecutá:

```bash
git clone https://github.com/TU_USUARIO/TU_REPO.git
cd TU_REPO
```

**Opción B — descarga directa:**

En GitHub, hacé clic en el botón verde **"Code"** → **"Download ZIP"**.
Descomprimí el ZIP en la carpeta que prefieras.

Luego abrí una terminal y navegá a esa carpeta:

```bash
# Windows (reemplazá la ruta con la tuya):
cd C:\Users\TuNombre\Downloads\MTG-Premodern

# macOS / Linux:
cd ~/Downloads/MTG-Premodern
```

### Paso 2 — Crear un entorno virtual (recomendado)

Un entorno virtual aísla las dependencias del proyecto para no interferir con otros
proyectos de Python en tu máquina.

```bash
# Crear el entorno:
python -m venv .venv

# Activarlo:
# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate
```

Cuando el entorno está activo, verás `(.venv)` al principio de la línea en la terminal.
**Tenés que activarlo cada vez que abras una terminal nueva para trabajar con el proyecto.**

### Paso 3 — Instalar dependencias

Con el entorno virtual activo:

```bash
pip install -r requirements.txt
```

Esto puede tardar unos minutos la primera vez.

### Paso 4 — Obtener la base de datos

Descargá `premodern.db` desde la sección **Releases** de este repositorio en GitHub
y colocala en la carpeta `db/` del proyecto:

```
MTG-Premodern/
└── db/
    └── premodern.db   ← acá va el archivo
```

### Paso 5 — Correr el dashboard

```bash
streamlit run dashboard/app.py
```

Se va a abrir automáticamente el navegador en `http://localhost:8501`.
Si no se abre solo, copiá esa dirección en tu navegador.

Para detener el dashboard, presioná `Ctrl+C` en la terminal.

---

## Inicio rápido (resumen)

```bash
# 1. Clonar
git clone https://github.com/TU_USUARIO/TU_REPO.git
cd TU_REPO

# 2. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar premodern.db a db/premodern.db

# 5. Correr el dashboard
streamlit run dashboard/app.py
```

---

## Actualizar la base de datos

La base se publica regularmente en Releases. Para actualizar tu copia local,
descargá la nueva versión y ejecutá:

```bash
python db/safe_ingest.py ruta/al/archivo/descargado/premodern.db
```

---

## Flujo de scraping desde cero

Si querés construir tu propia base de datos en lugar de usar la publicada, podés correr
los scripts **localmente o desde Google Colab**. El scraping no requiere Colab — todos los
headers necesarios para acceder a tcdecks.net ya están configurados en los scripts.
Colab es simplemente una opción cómoda para corridas largas (el scraping completo puede
tardar varias horas) sin ocupar tu máquina.

### Paso 1 — Scraping completo (primera vez)

**Opción A — local** (requiere tener instaladas las dependencias):

```bash
python scraper/results_scraper.py db/premodern.db   # torneos y mazos
python scraper/deck_scraper.py db/premodern.db       # cartas de cada mazo
python db/sync_scryfall.py db/premodern.db           # metadata y precios (Scryfall)
```

**Opción B — Google Colab**:

1. Abrí `notebooks/01_scrape_metadata.ipynb` en [Google Colab](https://colab.research.google.com)
   - Scrapea todos los torneos y mazos de tcdecks.net
   - Genera `premodern.db` con las tablas `tournaments` y `decks`
   - Al terminar, descargá el archivo desde el panel de archivos de Colab

2. Abrí `notebooks/02_scrape_cards.ipynb` en Colab
   - Subí la `premodern.db` del paso anterior al panel de archivos de Colab
   - Scrapea la lista de cartas de cada mazo
   - Sincroniza metadata con la API de Scryfall (CMC, tipo, precio mínimo USD, imagen)
   - Al terminar, descargá el archivo actualizado

3. Copiá el archivo a `db/premodern.db` en tu máquina local

### Paso 2 — Actualizaciones incrementales

**Local:**

```bash
python scraper/results_scraper.py db/premodern.db   # solo torneos nuevos
python scraper/deck_scraper.py db/premodern.db       # solo mazos sin cartas
python db/sync_scryfall.py db/premodern.db --prices-only   # refrescar precios
```

**Colab:** usá `notebooks/03_incremental_update.ipynb`:

1. Subí `db/premodern.db`
2. Corré todas las celdas
3. Descargá la base actualizada
4. Reemplazala localmente: `python db/safe_ingest.py ruta/a/premodern_descargada.db`

### Configurar el User-Agent de Scryfall

La [política de la API de Scryfall](https://scryfall.com/docs/api) pide que identifiques
tu aplicación. Antes de correr los notebooks, editá el User-Agent en `db/sync_scryfall.py`
(línea 127) y en la celda correspondiente de los notebooks:

```python
"User-Agent": "MTGPremodernAnalytics/1.0 (github.com/TU_USUARIO/TU_REPO)",
```

Reemplazá `TU_USUARIO/TU_REPO` con tu nombre de usuario y repositorio de GitHub.

---

## Análisis geográfico (opcional)

Para habilitar la página de análisis regional (07) y el filtro de país, ejecutá:

```bash
python db/detect_location.py db/premodern.db --stats
```

Para asignar ubicaciones manualmente a torneos no identificados:

```bash
# Ver qué torneos no tienen ubicación identificada
python db/detect_location.py db/premodern.db --list-unknown

# Editá db/location_overrides.json y agregá los que conozcas:
# { "12345": {"country": "Argentina", "city": "Buenos Aires"} }

# Volver a procesar con los nuevos overrides
python db/detect_location.py db/premodern.db --reprocess --stats
```

---

## Corrección de nombres de cartas (opcional)

Si hay cartas con typos que no se encontraron en Scryfall:

```bash
# Ver cartas no encontradas
python db/fix_card_names.py db/premodern.db --list

# Editá CORRECTIONS en db/fix_card_names.py y aplicá:
python db/fix_card_names.py db/premodern.db --apply

# Re-sincronizá metadata para las cartas corregidas
python db/sync_scryfall.py db/premodern.db --metadata-only
```

---

## Estado de la base de datos publicada

| | |
|---|---|
| Última actualización | 16 de junio de 2026 |
| Torneos | 4.408 |
| Mazos | 38.927 |
| Cartas únicas | 2.700 |
| Rango de fechas | 2018 → presente |
| Metadata Scryfall | CMC, tipo, colores, precio mínimo USD, imagen |
| Análisis geográfico | 16 países identificados (~54% de torneos paper) |

---

## Dashboard — páginas

| Página | Contenido |
|---|---|
| **Home** | Métricas globales, última actualización, top arquetipos, actividad mensual |
| **01 Meta Overview** | Tier list con precios, meta share, popularidad vs éxito, precio vs éxito, meta por fuente y por país |
| **02 Temporal** | Evolución del meta (stacked area), heatmap mensual, breakouts, tendencia por arquetipo |
| **03 Arquetipos** | Deep dive: métricas, mana curve, precio promedio del mazo (main+side), core/flex/sideboard con precio y % éxito, últimos resultados |
| **04 Cartas** | Top cartas con precio mínimo, búsqueda, distribución por tipo, breakouts, tendencias |
| **05 Jugadores** | Scatter especialistas vs experimentadores, leaderboard, perfil individual |
| **06 ML Insights** | Forecast de meta, clustering UMAP+HDBSCAN, co-ocurrencia de cartas (PMI, grafo), modelo de reacción |
| **07 Regional** | Volumen por país, comparación de meta, evolución de arquetipos por país, últimos torneos. Se basa en la ubicación geográfica de cada torneo, que en muchos casos no está disponible (especialmente torneos online y de Discord). Los datos pueden estar sesgados hacia comunidades con mayor presencia en torneos presenciales reportados. |

Todos los filtros del sidebar (fecha, fuente, país, tamaño mínimo de torneo) se aplican
a todas las páginas simultáneamente. Por defecto se muestran los **últimos 3 meses**.

---

## Schema de la base de datos

`db/premodern.db` (SQLite). Definición completa en [`db/schema.sql`](db/schema.sql).

**Tablas principales:**

| Tabla | Contenido |
|---|---|
| `tournaments` | Un torneo por fila: nombre, fecha, jugadores, fuente (paper/webcam/mol), país, ciudad |
| `decks` | Un mazo por fila: arquetipo, jugador, posición, total_players, si tiene cartas scrapeadas |
| `cards` | Una carta única: metadata Scryfall (CMC, tipo, colores, precio mínimo USD, imagen) |
| `deck_cards` | Relación mazo ↔ carta: cantidad, si es sideboard |
| `card_price_history` | Historial de precios: una fila por carta por corrida de sincronización |

**Vistas:**

| Vista | Contenido |
|---|---|
| `v_meta_share` | % meta share por arquetipo y mes |
| `v_archetype_success` | Top 8/4/1 rate y posición relativa por arquetipo |
| `v_card_popularity` | Popularidad de cartas (main y side por separado) |
| `v_player_stats` | Estadísticas por jugador |

---

## Estructura del repositorio

```
notebooks/
  01_scrape_metadata.ipynb     Scraping inicial de torneos y mazos (Colab)
  02_scrape_cards.ipynb        Scraping de cartas + sync Scryfall (Colab)
  03_incremental_update.ipynb  Actualización incremental (Colab)

db/
  schema.sql                   Definición de tablas, vistas e índices
  sync_scryfall.py             Sincronización con la API de Scryfall
  safe_ingest.py               Reemplazo seguro de la DB local
  fix_card_names.py            Corrección de typos en nombres de cartas
  detect_location.py           Detección de país/ciudad por nombre de torneo
  location_overrides.json      Overrides manuales de ubicación de torneos

analysis/
  meta_evolution.py            Meta share, tier list, breakouts
  success_metrics.py           Win rate / top8 por arquetipo
  card_trends.py               Tendencias y breakouts de cartas
  card_cooccurrence.py         Co-ocurrencia PMI y grafo de cartas
  archetype_clustering.py      TF-IDF + UMAP + HDBSCAN
  predictive.py                Forecast y modelo de reacción (Random Forest)
  mana_curve.py                Curva de maná promedio por arquetipo

dashboard/
  app.py                       Home
  db.py                        Conexión cacheada a la DB
  components/
    filters.py                 Filtros del sidebar
    charts.py                  Gráficos Plotly reutilizables
  pages/
    01_meta_overview.py … 07_regional.py

config/
  settings.py                  Constantes globales

scraper/                       Módulos de scraping (usados desde notebooks)
tests/
requirements.txt
.gitignore
```

---

## Solución de problemas frecuentes

**`python` no se reconoce como comando (Windows)**
→ Reinstalá Python desde [python.org](https://www.python.org/downloads/) marcando
  **"Add Python to PATH"** durante la instalación. Luego cerrá y volvé a abrir la terminal.

**`streamlit` no se reconoce como comando**
→ El entorno virtual no está activo. Ejecutá `.venv\Scripts\activate` (Windows) o
  `source .venv/bin/activate` (macOS/Linux) antes de correr el dashboard.

**Error al abrir el dashboard: `db/premodern.db` no encontrado**
→ Asegurate de haber descargado el archivo desde Releases y colocado en `db/premodern.db`.

**El navegador no se abre solo**
→ Copiá `http://localhost:8501` en la barra de dirección de tu navegador.

**UnicodeDecodeError al correr scripts en Windows**
→ Abrí la terminal con codificación UTF-8: `chcp 65001` antes de correr el script,
  o configurá `PYTHONUTF8=1` en las variables de entorno de tu sistema.

---

## Notas técnicas

- El scraping usa `requests` con cookie `verificado=1` y header
  `Accept-Encoding: gzip, deflate, br` (sin este header tcdecks.net devuelve 403).
- La DB usa `journal_mode=WAL`. Los notebooks hacen `PRAGMA wal_checkpoint(TRUNCATE)`
  antes de descargar para evitar corrupción del archivo.
- El dashboard cachea la conexión (`@st.cache_resource`) y las queries (`@st.cache_data`).
- Los precios se obtienen buscando en **todas las impresiones** de cada carta via
  `/cards/search?unique=prints` y tomando el mínimo USD disponible.
- Las cartas dobles (ej: `Fire // Ice`) se buscan por la primera cara y se almacenan
  bajo el nombre completo original.
- Todas las rutas usan `pathlib.Path` — el proyecto funciona igual en Windows,
  macOS y Linux sin ningún cambio de configuración.





## Licencia

- **Código**: [MIT License](LICENSE)
- **Datos** (`premodern.db`): [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

Los datos de torneos provienen de [tcdecks.net](https://www.tcdecks.net).
Al usar los datos, por favor incluí una referencia a este repositorio.
