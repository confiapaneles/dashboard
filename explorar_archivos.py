import os
import pandas as pd
from dbfread import DBF

DB_PATH = r'C:\Users\acaci\OneDrive\Documentos\PANELES_CONFIA\dbf'


def listar_dbf():
    print("\n📂 ARCHIVOS DBF ENCONTRADOS:\n")
    for f in os.listdir(DB_PATH):
        if f.lower().endswith('.dbf'):
            print(" -", f)


def mostrar_campos(nombre_dbf):
    path = os.path.join(DB_PATH, nombre_dbf)
    if not os.path.exists(path):
        print("❌ Archivo no encontrado")
        return

    table = DBF(path, encoding='latin1')
    df = pd.DataFrame(iter(table))

    print("\n📄 ARCHIVO:", nombre_dbf)
    print("📊 Registros:", len(df))
    print("\n🧱 CAMPOS:\n")

    for col in df.columns:
        print(f" - {col:<20} | tipo: {df[col].dtype}")

    print("\n🔍 EJEMPLO DE DATOS:")
    print(df.head(10
    ))


if __name__ == "__main__":
    while True:
        print("\n================================")
        print(" EXPLORADOR DBF - CONFIA ")
        print("================================")
        print("1. Listar DBF")
        print("2. Ver campos de un DBF")
        print("3. Salir")

        op = input("Opción: ").strip()

        if op == "1":
            listar_dbf()
        elif op == "2":
            nombre = input("Nombre del archivo (ej: tablero_facturas.DBF): ").strip()
            mostrar_campos(nombre)
        elif op == "3":
            break
        else:
            print("❌ Opción inválida")
