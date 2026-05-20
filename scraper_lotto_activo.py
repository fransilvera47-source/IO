#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Scraper de Lotto Activo — Resultados de Animalitos
=============================================================================
 Autor:       Francisco (generado con asistencia de IA)
 Descripción: Extrae resultados de Lotto Activo desde la API interna de
              lottoactivo.com y los almacena en Google Sheets.
 
 Modos de ejecución:
   --modo historico   → Carga los últimos 90 días de resultados
   --modo diario      → Solo extrae los resultados del día actual
 
 Uso:
   python scraper_lotto_activo.py --modo diario
   python scraper_lotto_activo.py --modo historico
   python scraper_lotto_activo.py --modo historico --dias 30
=============================================================================
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import gspread
import requests
from google.oauth2.service_account import Credentials

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTES
# =============================================================================

# Endpoint de la API interna de lottoactivo.com
API_URL = "https://lottoactivo.com/core/process.php"

# Token de la API para obtener resultados de animalitos por fecha.
API_TOKEN_RESULTADOS = (
    "R29pZ0dPVHZjRGczc0lOVVNVYm81ZyQvajlnYlVlN05IdEJobWk1dmhSalM5"
    "TjkyMVczbDlkVkJnTzZpWHU3SFRySTJKd09sc0RzQ01QZG9TWVJPVnZjSVJR"
    "ekRhSWx5REJGTlZibXZSRDc1UT09"
)

# Identificador del juego en la API
LOTERIA_ID = "lotto_activo"

# Scopes necesarios para Google Sheets
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Nombre por defecto de la hoja de cálculo
DEFAULT_SPREADSHEET_NAME = "Lotto Activo - Resultados"

# Nombre de la pestaña/hoja dentro del spreadsheet
WORKSHEET_NAME = "Resultados"

# Encabezados de las columnas en Google Sheets
HEADERS = ["Fecha", "Hora", "Animalito", "Numero", "Juego", "FechaHora_ID"]

# Configuración de reintentos para la API
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# Pausa entre peticiones para no sobrecargar el servidor (en segundos)
DELAY_ENTRE_PETICIONES = 2


# =============================================================================
# FUNCIONES DE SCRAPING
# =============================================================================

def obtener_resultados_por_fecha(fecha: str, session: requests.Session) -> list:
    """
    Consulta la API interna de lottoactivo.com para obtener los resultados
    de animalitos de una fecha específica.
    """
    payload = {
        "option": API_TOKEN_RESULTADOS,
        "loteria": LOTERIA_ID,
        "fecha": fecha,
    }

    for intento in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(
                API_URL,
                data=payload,
                timeout=30,
            )
            response.raise_for_status()

            datos_json = response.json()
            resultados_crudos = datos_json.get("datos", [])

            if not resultados_crudos:
                logger.info(f"  Sin resultados para {fecha}")
                return []

            # Transformar los datos crudos al formato que necesitamos
            resultados = []
            for item in resultados_crudos:
                nombre_animal = item.get("name_animal", "").strip()
                numero = item.get("number_animal", "")
                hora = item.get("time_s", "").strip()
                juego = item.get("name_game", "Lotto Activo").strip()

                # Crear el ID único para anti-duplicados
                fecha_hora_id = f"{fecha}_{hora}"

                resultados.append({
                    "Fecha": fecha,
                    "Hora": hora,
                    "Animalito": nombre_animal,
                    "Numero": str(numero),
                    "Juego": juego,
                    "FechaHora_ID": fecha_hora_id,
                })

            logger.info(
                f"  ✅ {fecha}: {len(resultados)} resultados obtenidos"
            )
            return resultados

        except requests.exceptions.RequestException as e:
            logger.warning(
                f"  ⚠️  Intento {intento}/{MAX_RETRIES} fallido para "
                f"{fecha}: {e}"
            )
            if intento < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * intento)
            else:
                logger.error(
                    f"  ❌ No se pudieron obtener resultados para {fecha} "
                    f"después de {MAX_RETRIES} intentos."
                )
                return []

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                f"  ❌ Error al procesar la respuesta para {fecha}: {e}"
            )
            return []

    return []


def scrape_rango_fechas(fecha_inicio: str, fecha_fin: str) -> list:
    """FASE 1: Carga Histórica."""
    inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    fin = datetime.strptime(fecha_fin, "%Y-%m-%d")

    logger.info(f"📅 Carga histórica: {fecha_inicio} → {fecha_fin}")
    
    todos_los_resultados = []
    session = _crear_session()
    fecha_actual = inicio
    
    while fecha_actual <= fin:
        fecha_str = fecha_actual.strftime("%Y-%m-%d")
        resultados_dia = obtener_resultados_por_fecha(fecha_str, session)
        todos_los_resultados.extend(resultados_dia)
        time.sleep(DELAY_ENTRE_PETICIONES)
        fecha_actual += timedelta(days=1)

    if todos_los_resultados:
        logger.info(f"\n📊 Total de registros obtenidos: {len(todos_los_resultados)}")
    else:
        logger.warning("⚠️  No se obtuvieron resultados en el rango.")
        
    return todos_los_resultados


def scrape_hoy() -> list:
    """FASE 2: Ejecución Diaria."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"📅 Scraping diario para: {hoy}")

    session = _crear_session()
    resultados = obtener_resultados_por_fecha(hoy, session)

    if resultados:
        logger.info(f"📊 Resultados del día: {len(resultados)} registros")
    else:
        logger.info("ℹ️  No hay resultados disponibles aún para hoy.")
        
    return resultados


def _crear_session() -> requests.Session:
    """Crea una sesión de requests con headers que simulan un navegador."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://lottoactivo.com",
        "Referer": "https://lottoactivo.com/resultados/lotto_activo/",
        "X-Requested-With": "XMLHttpRequest",
    })
    return session


# =============================================================================
# FUNCIONES DE GOOGLE SHEETS
# =============================================================================

def conectar_google_sheets(nombre_spreadsheet: str):
    """Establece conexión con Google Sheets usando Service Account."""
    cred_path = "credentials.json"
    if not os.path.exists(cred_path):
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if not cred_path or not os.path.exists(cred_path):
            logger.error(
                "❌ No se encontró el archivo de credenciales.\n"
                "   Coloca 'credentials.json' en el directorio actual o\n"
                "   configura la variable GOOGLE_APPLICATION_CREDENTIALS."
            )
            sys.exit(1)

    logger.info(f"🔑 Autenticando con Google usando: {cred_path}")

    credentials = Credentials.from_service_account_file(
        cred_path, scopes=GOOGLE_SCOPES
    )
    cliente = gspread.authorize(credentials)

    try:
        spreadsheet = cliente.open(nombre_spreadsheet)
        logger.info(f"📗 Spreadsheet encontrado: '{nombre_spreadsheet}'")
    except gspread.SpreadsheetNotFound:
        logger.error(
            f"❌ No se encontró la hoja '{nombre_spreadsheet}'.\n"
            f"   Asegúrate de:\n"
            f"   1. Crear la hoja en Google Sheets\n"
            f"   2. Compartirla con el email de la Service Account\n"
            f"      (aparece en credentials.json como 'client_email')"
        )
        sys.exit(1)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        logger.info(f"📋 Pestaña encontrada: '{WORKSHEET_NAME}'")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME, rows=1000, cols=len(HEADERS)
        )
        worksheet.append_row(HEADERS)
        logger.info(f"📋 Pestaña creada: '{WORKSHEET_NAME}' con encabezados")

    return spreadsheet, worksheet


def leer_datos_existentes(worksheet: gspread.Worksheet) -> list:
    """Lee todos los datos existentes en la hoja de Google Sheets."""
    registros = worksheet.get_all_records()
    if registros:
        logger.info(f"📖 Registros existentes en la hoja: {len(registros)}")
        return registros
    else:
        logger.info("📖 La hoja está vacía (sin registros previos).")
        return []


def filtrar_duplicados(datos_nuevos: list, datos_existentes: list) -> list:
    """Filtra los datos nuevos comparando la clave FechaHora_ID."""
    if not datos_nuevos:
        return []

    if not datos_existentes:
        logger.info("   → Todos los datos son nuevos (hoja vacía).")
        return datos_nuevos

    # Obtener los IDs de Fecha+Hora que ya existen
    ids_existentes = set(str(fila.get("FechaHora_ID", "")) for fila in datos_existentes)

    # Filtrar: solo conservar los que NO están en la hoja
    datos_unicos = [
        fila for fila in datos_nuevos 
        if str(fila.get("FechaHora_ID", "")) not in ids_existentes
    ]

    total_nuevos = len(datos_nuevos)
    total_unicos = len(datos_unicos)
    duplicados = total_nuevos - total_unicos

    logger.info(
        f"🔍 Anti-duplicados: {total_nuevos} scrapeados → "
        f"{duplicados} duplicados descartados → "
        f"{total_unicos} nuevos para insertar"
    )

    return datos_unicos


def escribir_en_sheets(worksheet: gspread.Worksheet, datos: list) -> None:
    """Escribe los datos nuevos en Google Sheets."""
    if not datos:
        logger.info("ℹ️  No hay datos nuevos para escribir.")
        return

    # Verificar que los encabezados existen
    encabezados_actuales = worksheet.row_values(1)
    if not encabezados_actuales:
        worksheet.append_row(HEADERS)
        logger.info("📝 Encabezados escritos en la hoja.")

    # Convertir diccionarios a lista de listas basándonos en el orden de HEADERS
    filas = []
    for d in datos:
        fila = [d.get(h, "") for h in HEADERS]
        filas.append(fila)

    # Escribir en lotes para evitar límites de la API de Google
    BATCH_SIZE = 100
    total_escritos = 0

    for i in range(0, len(filas), BATCH_SIZE):
        lote = filas[i : i + BATCH_SIZE]
        worksheet.append_rows(lote, value_input_option="USER_ENTERED")
        total_escritos += len(lote)
        logger.info(f"   📝 Escritos {total_escritos}/{len(filas)} registros...")
        if i + BATCH_SIZE < len(filas):
            time.sleep(1)

    logger.info(f"✅ {total_escritos} registros escritos exitosamente.")


# =============================================================================
# FUNCIÓN PRINCIPAL (ORQUESTADOR)
# =============================================================================

def ejecutar(modo: str, dias: int = 90) -> None:
    logger.info("=" * 60)
    logger.info("🎰 SCRAPER DE LOTTO ACTIVO — INICIO")
    logger.info(f"   Modo: {modo.upper()}")
    logger.info("=" * 60)

    if modo == "historico":
        hoy = datetime.now()
        fecha_inicio = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
        fecha_fin = hoy.strftime("%Y-%m-%d")
        datos_nuevos = scrape_rango_fechas(fecha_inicio, fecha_fin)
    elif modo == "diario":
        datos_nuevos = scrape_hoy()
    else:
        logger.error(f"❌ Modo no reconocido: '{modo}'. Usa 'historico' o 'diario'.")
        sys.exit(1)

    if not datos_nuevos:
        logger.info("ℹ️  No se obtuvieron resultados. Finalizando.")
        return

    nombre_sheet = os.environ.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET_NAME)
    spreadsheet, worksheet = conectar_google_sheets(nombre_sheet)

    datos_existentes = leer_datos_existentes(worksheet)
    datos_sin_duplicados = filtrar_duplicados(datos_nuevos, datos_existentes)

    escribir_en_sheets(worksheet, datos_sin_duplicados)

    logger.info("=" * 60)
    logger.info("🎰 SCRAPER DE LOTTO ACTIVO — FIN")
    logger.info("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scraper de resultados de Lotto Activo (Animalitos)",
    )
    parser.add_argument(
        "--modo", type=str, required=True, choices=["historico", "diario"],
    )
    parser.add_argument(
        "--dias", type=int, default=90,
    )
    args = parser.parse_args()
    ejecutar(modo=args.modo, dias=args.dias)
