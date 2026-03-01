import os
from dbfread import DBF
import pandas as pd

# Configuración de la ruta (ajusta si tu carpeta tiene otro nombre)
DBF_DIR = os.path.join(os.path.dirname(__file__), 'dbf')

def inspeccionar_tablas():
    if not os.path.exists(DBF_DIR):
        print(f"❌ No se encontró la carpeta: {DBF_DIR}")
        return

    print(f"🔍 Escaneando archivos en: {DBF_DIR}\n")
    print("-" * 60)

    archivos = [f for f in os.listdir(DBF_DIR) if f.lower().endswith('.dbf')]
    
    for archivo in archivos:
        path = os.path.join(DBF_DIR, archivo)
        try:
            # Cargamos solo el primer registro para ver la estructura
            table = DBF(path, encoding='latin-1', load=False)
            df = pd.DataFrame(iter(table))
            
            if df.empty:
                print(f"📁 Archivo: {archivo} (VACÍO)")
                continue

            print(f"📁 ARCHIVO: {archivo}")
            print(f"📊 Total Registros: {len(table)}")
            print("🧱 CAMPOS DETECTADOS:")
            
            # Listamos campos y mostramos el valor del primer registro para comparar
            for col in df.columns:
                valor_ejemplo = str(df[col].iloc[0]).strip()
                tipo = df[col].dtype
                print(f"  - {col:15} | Tipo: {str(tipo):10} | Ejemplo: {valor_ejemplo[:40]}")
            
            print("-" * 60)

        except Exception as e:
            print(f"⚠️ Error leyendo {archivo}: {e}")

if __name__ == "__main__":
    inspeccionar_tablas()