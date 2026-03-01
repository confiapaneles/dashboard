import pandas as pd
from dbfread import DBF
import os

# Ruta a tu base de datos de usuarios
RUTA_USUARIOS = r"C:\Users\acaci\OneDrive\Documentos\PANELES_CONFIA\dbf\tablero_usuarios.DBF"

def ver_campos_y_datos():
    if not os.path.exists(RUTA_USUARIOS):
        print(f"Error: El archivo no existe en {RUTA_USUARIOS}")
        return

    try:
        # Cargamos el archivo
        tabla = DBF(RUTA_USUARIOS, encoding='latin-1', load=True)
        df = pd.DataFrame(tabla)
        
        # 1. Ver Nombres de Columnas (Campos)
        print("\n" + "="*50)
        print("📋 ESTRUCTURA DE LA TABLA (CAMPOS):")
        print("="*50)
        for i, columna in enumerate(df.columns):
            print(f"Campo {i+1}: {columna}")

        # 2. Ver Contenido Completo (Usuarios y Niveles)
        print("\n" + "="*50)
        print("👥 DATOS DE LOS USUARIOS:")
        print("="*50)
        # Limpiamos espacios para que se vea bien en la terminal
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        print(df.to_string(index=False))
        print("="*50 + "\n")

    except Exception as e:
        print(f"Ocurrió un error al leer: {e}")

if __name__ == "__main__":
    ver_campos_y_datos()