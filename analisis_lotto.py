import os
import sys
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "Lotto Activo - Resultados")
WORKSHEET_NAME = "Resultados"

HTML_FILENAME = "dashboard_lotto.html"

# =============================================================================
# CONEXIÓN A GOOGLE SHEETS
# =============================================================================
def conectar_sheets() -> list:
    cred_path = "credentials.json"
    if not os.path.exists(cred_path):
        logger.error("❌ No se encontró credentials.json.")
        sys.exit(1)

    credentials = Credentials.from_service_account_file(cred_path, scopes=GOOGLE_SCOPES)
    cliente = gspread.authorize(credentials)

    try:
        spreadsheet = cliente.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        logger.info("⬇️ Descargando miles de registros... por favor espera.")
        records = worksheet.get_all_records()
        if not records:
            logger.error("La hoja de cálculo está vacía.")
            sys.exit(1)
        return records
    except Exception as e:
        logger.error(f"❌ Error al conectar con Google Sheets: {e}")
        sys.exit(1)

# =============================================================================
# PROCESAMIENTO ESTADÍSTICO PURO (SIN PANDAS)
# =============================================================================
def procesar_datos(records):
    logger.info("⚙️ Limpiando y ordenando datos...")
    # Filtrar válidos y parsear fecha/hora real
    datos_limpios = []
    for r in records:
        f_str = r.get("Fecha", "")
        h_str = r.get("Hora", "")
        animal = r.get("Animalito", "")
        if f_str and h_str and animal:
            try:
                # Ej: 2025-07-01 09:00 AM
                dt = datetime.strptime(f"{f_str} {h_str}", "%Y-%m-%d %I:%M %p")
                datos_limpios.append({
                    "dt": dt,
                    "animal": animal.strip(),
                    "hora": h_str
                })
            except Exception:
                pass
                
    # Ordenar cronológicamente (vital para Markov y Frios)
    datos_limpios.sort(key=lambda x: x["dt"])
    return datos_limpios

def calcular_estadisticas(datos):
    logger.info("🧮 Calculando estadística y probabilidades...")
    
    # 1. Frecuencias Globales
    conteo_global = Counter([d["animal"] for d in datos])
    # Ordenar de mayor a menor
    top_globales = conteo_global.most_common()
    
    # 2. Cadenas de Markov (Transiciones)
    transiciones = defaultdict(Counter)
    for i in range(len(datos) - 1):
        actual = datos[i]["animal"]
        siguiente = datos[i+1]["animal"]
        transiciones[actual][siguiente] += 1
        
    # Calcular probabilidades para tabla
    matriz_markov = []
    animales_unicos = sorted(list(conteo_global.keys()))
    for a_actual in animales_unicos:
        total_salidas = sum(transiciones[a_actual].values())
        fila = {"animal": a_actual, "destinos": {}}
        for a_sig in animales_unicos:
            veces = transiciones[a_actual].get(a_sig, 0)
            prob = round((veces / total_salidas * 100), 2) if total_salidas > 0 else 0
            fila["destinos"][a_sig] = prob
        matriz_markov.append(fila)
        
    # 3. Animales Frios (Más sorteos sin salir)
    ultimo_sorteo_idx = len(datos)
    ultima_aparicion = {}
    for idx, d in enumerate(datos):
        ultima_aparicion[d["animal"]] = idx
        
    frios = []
    for animal, idx in ultima_aparicion.items():
        sorteos_sin_salir = ultimo_sorteo_idx - idx - 1
        frios.append({"animal": animal, "espera": sorteos_sin_salir})
    
    frios.sort(key=lambda x: x["espera"], reverse=True)
    
    return {
        "globales_labels": [x[0] for x in top_globales],
        "globales_data": [x[1] for x in top_globales],
        "markov": matriz_markov,
        "frios_labels": [x["animal"] for x in frios[:15]],
        "frios_data": [x["espera"] for x in frios[:15]],
        "total_sorteos": len(datos)
    }

# =============================================================================
# GENERADOR DEL DASHBOARD HTML
# =============================================================================
def generar_html(stats):
    logger.info("🎨 Generando Dashboard Interactivo...")
    
    # Variables a inyectar
    json_globales_labels = json.dumps(stats["globales_labels"])
    json_globales_data = json.dumps(stats["globales_data"])
    json_frios_labels = json.dumps(stats["frios_labels"])
    json_frios_data = json.dumps(stats["frios_data"])
    total = stats["total_sorteos"]
    
    # Generar tabla Markov en HTML
    animales = sorted([m["animal"] for m in stats["markov"]])
    tabla_html = "<table class='min-w-full text-xs text-center border-collapse'>"
    
    # Cabecera
    tabla_html += "<thead><tr class='bg-gray-800 text-white'><th>Actual \\ Sig</th>"
    for a in animales:
        # Abreviar nombre para que quepa (ej: "Delfín" -> "Del")
        tabla_html += f"<th class='p-1 border border-gray-700' title='{a}'>{a[:3]}</th>"
    tabla_html += "</tr></thead><tbody>"
    
    # Filas
    for fila in stats["markov"]:
        a_actual = fila["animal"]
        tabla_html += f"<tr><td class='p-1 font-bold bg-gray-800 text-white border border-gray-700'>{a_actual[:3]}</td>"
        for a_sig in animales:
            prob = fila["destinos"].get(a_sig, 0)
            # Escala de color simple basada en probabilidad
            if prob > 4: bg = "bg-red-500 text-white font-bold"
            elif prob > 3: bg = "bg-orange-400"
            elif prob > 2: bg = "bg-yellow-300"
            elif prob > 0: bg = "bg-green-200"
            else: bg = "bg-gray-100 text-gray-400"
            tabla_html += f"<td class='p-1 border border-gray-300 {bg}' title='Si sale {a_actual}, hay {prob}% de que el siguiente sea {a_sig}'>{prob}%</td>"
        tabla_html += "</tr>"
    tabla_html += "</tbody></table>"

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Analítico: Lotto Activo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-50 p-6 font-sans">
    <div class="max-w-7xl mx-auto">
        <header class="mb-8 text-center">
            <h1 class="text-4xl font-extrabold text-blue-900 mb-2">📊 Lotto Activo - Data Science Dashboard</h1>
            <p class="text-gray-600 text-lg">Análisis estadístico basado en <b>{total} sorteos históricos</b>.</p>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- Gráfico 1: Globales -->
            <div class="bg-white p-6 rounded-xl shadow-lg border border-gray-100">
                <h2 class="text-xl font-bold text-gray-800 mb-4">🏆 Frecuencias Históricas (Más Salidores)</h2>
                <canvas id="chartGlobales" height="150"></canvas>
            </div>
            
            <!-- Gráfico 2: Fríos -->
            <div class="bg-white p-6 rounded-xl shadow-lg border border-gray-100">
                <h2 class="text-xl font-bold text-gray-800 mb-4">❄️ Top 15 Animales Fríos (Tiempo sin salir)</h2>
                <canvas id="chartFrios" height="150"></canvas>
            </div>
        </div>

        <!-- Matriz de Markov -->
        <div class="bg-white p-6 rounded-xl shadow-lg border border-gray-100 overflow-x-auto">
            <h2 class="text-xl font-bold text-gray-800 mb-2">🔗 Matriz de Transición de Markov (Probabilidad)</h2>
            <p class="text-sm text-gray-500 mb-4">Léelo así: Si acaba de salir el animal de la <b>fila izquierda</b>, ¿qué probabilidad hay de que el próximo sea el de la <b>columna de arriba</b>?</p>
            <div class="overflow-x-auto">
                {tabla_html}
            </div>
        </div>
    </div>

    <script>
        // Data inyectada desde Python
        const globalesLabels = {json_globales_labels};
        const globalesData = {json_globales_data};
        const friosLabels = {json_frios_labels};
        const friosData = {json_frios_data};

        // Gráfico Frecuencias
        new Chart(document.getElementById('chartGlobales'), {{
            type: 'bar',
            data: {{
                labels: globalesLabels,
                datasets: [{{
                    label: 'Veces que ha salido',
                    data: globalesData,
                    backgroundColor: 'rgba(59, 130, 246, 0.8)',
                    borderColor: 'rgba(37, 99, 235, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Gráfico Fríos
        new Chart(document.getElementById('chartFrios'), {{
            type: 'bar',
            data: {{
                labels: friosLabels,
                datasets: [{{
                    label: 'Sorteos seguidos sin salir',
                    data: friosData,
                    backgroundColor: 'rgba(239, 68, 68, 0.8)',
                    borderColor: 'rgba(220, 38, 38, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{ 
                responsive: true, 
                indexAxis: 'y', // Barras horizontales
                plugins: {{ legend: {{ display: false }} }} 
            }}
        }});
    </script>
</body>
</html>
"""
    with open(HTML_FILENAME, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    logger.info(f"✅ Dashboard generado exitosamente: {HTML_FILENAME}")
    logger.info(f"🌐 Para verlo, haz doble clic en {HTML_FILENAME} o arrástralo a tu navegador web.")

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    records = conectar_sheets()
    datos = procesar_datos(records)
    stats = calcular_estadisticas(datos)
    generar_html(stats)
