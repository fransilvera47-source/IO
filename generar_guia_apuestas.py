import os
import sys
import json
import csv
from collections import Counter, defaultdict
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "Lotto Activo - Resultados")
WORKSHEET_NAME = "Resultados"

def conectar_sheets():
    cred_path = "credentials.json"
    credentials = Credentials.from_service_account_file(cred_path, scopes=GOOGLE_SCOPES)
    cliente = gspread.authorize(credentials)
    return cliente.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME).get_all_records()

def main():
    print("Conectando a Google Sheets...")
    records = conectar_sheets()
    
    # Mapeo de Animal -> Número con excepciones predefinidas (para evitar que Sheets convierta 00 en 0)
    mapa_numeros = {
        "Delfin": "0",
        "Ballena": "00"
    }
    
    # Procesar datos
    datos = []
    for r in records:
        f_str = r.get("Fecha", "")
        h_str = r.get("Hora", "")
        animal = r.get("Animalito", "")
        numero = r.get("Numero", "")
        if f_str and h_str and animal:
            animal = animal.strip()
            if animal not in mapa_numeros and str(numero).strip() != "":
                mapa_numeros[animal] = str(numero).strip()
                
            try:
                dt = datetime.strptime(f"{f_str} {h_str}", "%Y-%m-%d %I:%M %p")
                datos.append({"dt": dt, "animal": animal})
            except Exception:
                pass
                
    datos.sort(key=lambda x: x["dt"])
    
    # Matriz de Transición
    transiciones = defaultdict(Counter)
    for i in range(len(datos) - 1):
        actual = datos[i]["animal"]
        siguiente = datos[i+1]["animal"]
        transiciones[actual][siguiente] += 1
        
    recomendaciones = {}
    animales_unicos = sorted(list(set(d["animal"] for d in datos)))
    
    for a_actual in animales_unicos:
        total_salidas = sum(transiciones[a_actual].values())
        if total_salidas == 0:
            continue
            
        a_jugar = []
        for a_sig in animales_unicos:
            prob = round((transiciones[a_actual].get(a_sig, 0) / total_salidas * 100), 2)
            if prob > 2.0:
                a_jugar.append((a_sig, prob))
        
        a_jugar.sort(key=lambda x: x[1], reverse=True)
        recomendaciones[a_actual] = a_jugar

    # Escribir reporte Markdown numérico
    with open("guia_apuestas.md", "w", encoding="utf-8") as f:
        f.write("# 🎯 Guía Maestra de Apuestas (Numérica)\n\n")
        for animal, jugar_lista in recomendaciones.items():
            num_actual = mapa_numeros.get(animal, "??")
            f.write(f"### Si sale: **{num_actual}** ({animal})\n")
            numeros_a_jugar = [mapa_numeros.get(a[0], "??") for a in jugar_lista]
            lista_str = ", ".join(numeros_a_jugar)
            f.write(f"> **{lista_str}**\n\n")

    # Escribir archivo CSV para abrir en Excel
    # Usamos utf-8-sig para que Excel reconozca correctamente los acentos (BOM)
    with open("guia_apuestas_excel_corregida.csv", "w", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter=";")
        writer.writerow(["Numero de Referencia", "Animal de Referencia", "Cantidad a Jugar", "Numeros a Jugar (Orden de Probabilidad)"])
        
        for animal, jugar_lista in recomendaciones.items():
            num_actual = mapa_numeros.get(animal, "??")
            numeros_a_jugar = [mapa_numeros.get(a[0], "??") for a in jugar_lista]
            lista_str = ", ".join(numeros_a_jugar)
            
            writer.writerow([num_actual, animal, len(jugar_lista), lista_str])

    print("Guía generada en guia_apuestas.md y guia_apuestas_excel.csv")

if __name__ == "__main__":
    main()
