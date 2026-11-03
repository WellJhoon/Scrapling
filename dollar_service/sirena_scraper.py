import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from scrapling.fetchers import FetcherSession

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "sirena_products.json"

BASE_URL = "https://www.sirena.do"
CATEGORY_TREE_URL = f"{BASE_URL}/api/catalog_system/pub/category/tree/3"
SEARCH_URL = f"{BASE_URL}/api/catalog_system/pub/products/search"

class SirenaScraper:
    """
    Scraper completo para La Sirena (sirena.do) basado en Scrapling.
    Extrae productos, precios, marcas, categorías e inventario y los almacena en un JSON local.
    """

    def __init__(self, impersonate: str = "chrome"):
        self.impersonate = impersonate
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_categories(self) -> List[Dict[str, Any]]:
        """Obtiene el árbol completo de categorías de La Sirena"""
        with FetcherSession(impersonate=self.impersonate, stealthy_headers=True) as session:
            resp = session.get(CATEGORY_TREE_URL)
            if resp.status == 200:
                return resp.json()
            return []

    def scrape_products(
        self,
        category_id: Optional[int] = 1, # 1 = Supermercado
        max_products: int = 100,
        batch_size: int = 50,
        delay_seconds: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Extrae productos paginados de La Sirena mediante Scrapling.
        :param category_id: ID de categoría (ej. 1 = Supermercado, None = Toda la tienda)
        :param max_products: Límite máximo de productos a recolectar
        :param batch_size: Cantidad de productos por página (máx recomendado VTEX: 50)
        :param delay_seconds: Tiempo de espera entre peticiones para no saturar
        """
        products: List[Dict[str, Any]] = []
        offset = 0

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando scraping de La Sirena (Categoría ID: {category_id})...")

        with FetcherSession(impersonate=self.impersonate, stealthy_headers=True) as session:
            while offset < max_products:
                limit = min(offset + batch_size - 1, max_products - 1)
                url = f"{SEARCH_URL}?_from={offset}&_to={limit}"
                if category_id:
                    url += f"&fq=C:{category_id}"

                resp = session.get(url)
                # VTEX responde con 200 o 206 (Partial Content)
                if resp.status not in (200, 206):
                    print(f"Error {resp.status} al consultar {url}")
                    break

                batch = resp.json()
                if not batch or len(batch) == 0:
                    print("No se encontraron más productos.")
                    break

                for raw in batch:
                    # Parsear datos comerciales del primer SKU/Seller
                    items = raw.get("items", [])
                    first_item = items[0] if items else {}
                    sellers = first_item.get("sellers", [])
                    comm_offer = sellers[0].get("commertialOffer", {}) if sellers else {}
                    images = first_item.get("images", [])

                    product_item = {
                        "id": raw.get("productId"),
                        "name": raw.get("productName"),
                        "brand": raw.get("brand"),
                        "link": raw.get("link"),
                        "categories": raw.get("categories", []),
                        "price": comm_offer.get("Price"),
                        "list_price": comm_offer.get("ListPrice"),
                        "available": comm_offer.get("AvailableQuantity", 0) > 0,
                        "available_quantity": comm_offer.get("AvailableQuantity", 0),
                        "image_url": images[0].get("imageUrl") if images else None,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    products.append(product_item)

                print(f"Recogidos {len(products)} de {max_products} productos...")
                offset += batch_size

                if len(batch) < (limit - offset + 1):
                    # Se acabó el catálogo
                    break

                time.sleep(delay_seconds)

        # Guardar en archivo JSON local
        self.save_to_json(products)
        return products

    def save_to_json(self, data: List[Dict[str, Any]], filepath: Path = OUTPUT_FILE):
        """Guarda la lista de productos en el archivo JSON local"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "store": "La Sirena (sirena.do)",
                "total_products": len(data),
                "generated_at": datetime.utcnow().isoformat(),
                "products": data
            }, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Archivo JSON guardado exitosamente en:\n  {filepath.resolve()}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scraper de productos de La Sirena (sirena.do)")
    parser.add_argument("--max", type=int, default=100, help="Cantidad máxima de productos a extraer (ej. 100, 500, 2000)")
    parser.add_argument("--category", type=int, default=1, help="ID de categoría (1: Supermercado, 2: Bebe, 3: Belleza, 4: Electrodomésticos, 6: Hogar)")
    args = parser.parse_args()

    scraper = SirenaScraper()
    scraper.scrape_products(category_id=args.category, max_products=args.max)
