import os
import pandas as pd
from dbfread import DBF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DBF_BASE = os.path.join(BASE_DIR, "dbf")


def listar_empresas():
    print("\n🏢 EMPRESAS DISPONIBLES:\n")
    empresas = [d for d in os.listdir(DBF_BASE) if os.path.isdir(os.path.join(DBF_BASE, d))]

    if not empresas:
        print("❌ No hay carpetas de empresas dentro de /dbf")
        return []

    for e in empresas:
        print(" -", e)

    return empresas


def listar_dbf(empresa):
    empresa_path = os.path.join(DBF_BASE, empresa)

    print(f"\n📂 ARCHIVOS DBF ENCONTRADOS EN: {empresa}\n")

    encontrados = False

    for root, dirs, files in os.walk(empresa_path):
        for f in files:
            if f.lower().endswith('.dbf'):
                encontrados = True
                ruta_relativa = os.path.relpath(os.path.join(root, f), empresa_path)
                print(" -", ruta_relativa)

    if not encontrados:
        print("❌ No se encontraron DBF en esta empresa.")


def mostrar_campos(empresa, nombre_dbf):
    empresa_path = os.path.join(DBF_BASE, empresa)

    # Buscar archivo en subcarpetas
    for root, dirs, files in os.walk(empresa_path):
        for f in files:
            if f.lower() == nombre_dbf.lower():
                path = os.path.join(root, f)
                break
        else:
            continue
        break
    else:
        print("❌ Archivo no encontrado en esta empresa.")
        return

    table = DBF(path, encoding='latin1')
    df = pd.DataFrame(iter(table))

    print("\n📄 ARCHIVO:", nombre_dbf)
    print("📊 Registros:", len(df))
    print("\n🧱 CAMPOS:\n")

    for col in df.columns:
        print(f" - {col:<20} | tipo: {df[col].dtype}")

    print("\n🔍 EJEMPLO DE DATOS:")
    print(df.head(10))


if __name__ == "__main__":
    empresa_actual = None

    while True:
        print("\n================================")
        print(" EXPLORADOR DBF - MULTIEMPRESA ")
        print("================================")
        print("1. Listar empresas")
        print("2. Seleccionar empresa")
        print("3. Listar DBF de la empresa seleccionada")
        print("4. Ver campos de un DBF")
        print("5. Salir")

        op = input("Opción: ").strip()

        if op == "1":
            listar_empresas()

        elif op == "2":
            empresas = listar_empresas()
            if empresas:
                empresa_actual = input("\nEscribe el nombre EXACTO de la empresa: ").strip()
                if empresa_actual not in empresas:
                    print("❌ Empresa no válida.")
                    empresa_actual = None
                else:
                    print(f"✔ Empresa seleccionada: {empresa_actual}")

        elif op == "3":
            if not empresa_actual:
                print("❌ Primero selecciona una empresa (opción 2).")
            else:
                listar_dbf(empresa_actual)

        elif op == "4":
            if not empresa_actual:
                print("❌ Primero selecciona una empresa (opción 2).")
            else:
                nombre = input("Nombre del archivo DBF (ej: facturas.dbf): ").strip()
                mostrar_campos(empresa_actual, nombre)

        elif op == "5":
            break

        else:
            print("❌ Opción inválida")
