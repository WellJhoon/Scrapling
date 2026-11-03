import sys
from pathlib import Path

# Agregar el directorio actual al path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import init_db, get_latest_rate
from scraper import BCRDScraper

def main():
    print("Iniciando scraper del dólar...")
    init_db()
    scraper = BCRDScraper()

    # 1. Obtener la tasa del día
    print("\nConsultando tasa oficial del día en el Banco Central...")
    today = scraper.fetch_today_rate()
    if today:
        print("✓ Tasa del día obtenida y guardada:")
        print(f"  • Fecha:   {today['date']}")
        print(f"  • Compra:  RD$ {today['purchase_rate']}")
        print(f"  • Venta:   RD$ {today['selling_rate']}")
    else:
        print("✗ No se pudo obtener la tasa del día.")

    # 2. Obtener historial reciente
    print("\nSincronizando últimos 7 días de historial...")
    history = scraper.fetch_historical_rates(days_back=7)
    print(f"✓ {len(history)} registros sincronizados con la base de datos.")

    # 3. Mostrar el último registro almacenado
    latest = get_latest_rate()
    print("\n[Último registro en SQLite]:")
    print(latest)

if __name__ == "__main__":
    main()
