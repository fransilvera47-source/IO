import os
import sys
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
        records = worksheet.get_all_records()
        return records
    except Exception as e:
        logger.error(f"❌ Error al conectar con Google Sheets: {e}")
        sys.exit(1)

# =============================================================================
# BACKTESTING
# =============================================================================
def ejecutar_backtest():
    records = conectar_sheets()
    
    # Limpieza
    datos = []
    for r in records:
        f_str = r.get("Fecha", "")
        h_str = r.get("Hora", "")
        animal = r.get("Animalito", "")
        if f_str and h_str and animal:
            try:
                dt = datetime.strptime(f"{f_str} {h_str}", "%Y-%m-%d %I:%M %p")
                datos.append({"dt": dt, "animal": animal.strip()})
            except Exception:
                pass
                
    # Ordenar cronológicamente
    datos.sort(key=lambda x: x["dt"])
    
    # 1. Calcular Matriz de Markov
    transiciones = defaultdict(Counter)
    for i in range(len(datos) - 1):
        actual = datos[i]["animal"]
        siguiente = datos[i+1]["animal"]
        transiciones[actual][siguiente] += 1
        
    probabilidades_markov = defaultdict(list)
    for a_actual, conteos_siguientes in transiciones.items():
        total_salidas = sum(conteos_siguientes.values())
        for a_sig, veces in conteos_siguientes.items():
            prob = round((veces / total_salidas * 100), 2) if total_salidas > 0 else 0
            if prob > 2.0: # Colores Amarillo, Naranja, Rojo
                probabilidades_markov[a_actual].append(a_sig)
                
    # 2. Bucle de Simulación
    balance_acumulado = 0.0
    peor_balance = 0.0
    
    apuesta_base = 0.5
    multiplicador_ganancia = 30
    
    apuesta_actual_por_animal = apuesta_base
    racha_perdidas_actual = 0
    peor_racha_perdidas = 0
    
    apuestas_realizadas = 0
    turnos_ganados = 0
    turnos_perdidos = 0
    
    # Empezamos desde el segundo sorteo (índice 1) porque necesitamos ver el anterior
    for i in range(1, len(datos)):
        animal_ayer = datos[i-1]["animal"]
        animal_hoy = datos[i]["animal"]
        
        # Estrategia: ¿A cuáles le apostamos hoy?
        animales_apuesta = probabilidades_markov.get(animal_ayer, [])
        
        if not animales_apuesta:
            continue # Si no hay ningún animal > 2%, no apostamos en este turno.
            
        apuestas_realizadas += 1
        costo_turno = apuesta_actual_por_animal * len(animales_apuesta)
        
        if animal_hoy in animales_apuesta:
            # Ganamos!
            turnos_ganados += 1
            premio = apuesta_actual_por_animal * multiplicador_ganancia
            profit = premio - costo_turno
            balance_acumulado += profit
            
            # Reset Martingala
            apuesta_actual_por_animal = apuesta_base
            racha_perdidas_actual = 0
            
        else:
            # Perdimos!
            turnos_perdidos += 1
            profit = -costo_turno
            balance_acumulado += profit
            
            # Multiplicador Martingala
            apuesta_actual_por_animal *= 2
            racha_perdidas_actual += 1
            if racha_perdidas_actual > peor_racha_perdidas:
                peor_racha_perdidas = racha_perdidas_actual
                
        # Calcular el peor drawdown (banca necesaria)
        if balance_acumulado < peor_balance:
            peor_balance = balance_acumulado
            
    logger.info("=======================================")
    logger.info("📊 RESULTADOS DEL BACKTESTING MARTINGALA")
    logger.info("=======================================")
    logger.info(f"Total de sorteos evaluados: {len(datos)}")
    logger.info(f"Total de turnos apostados: {apuestas_realizadas}")
    logger.info(f"Turnos Ganados: {turnos_ganados}")
    logger.info(f"Turnos Perdidos: {turnos_perdidos}")
    logger.info(f"Winrate Promedio: {round((turnos_ganados/apuestas_realizadas)*100, 2)}%")
    logger.info("---")
    logger.info(f"💰 Balance Final (Profit/Loss): {round(balance_acumulado, 2)} unidades")
    logger.info(f"📉 Peor momento de la Banca (Drawdown Máximo): {round(peor_balance, 2)} unidades")
    logger.info(f"🔥 Peor Racha de Pérdidas Consecutivas: {peor_racha_perdidas}")
    logger.info("=======================================")

if __name__ == "__main__":
    ejecutar_backtest()
