import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Set

from scrapling.fetchers import FetcherSession

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "sirena_all_products.json"
PROGRESS_FILE = OUTPUT_DIR / "sirena_scraper_progress.json"

BASE_URL = "https://www.sirena.do"
CATEGORY_TREE_URL = f"{BASE_URL}/api/catalog_system/pub/category/tree/3"
SEARCH_URL = f"{BASE_URL}/api/catalog_system/pub/products/search"

class FullSirenaScraper:
    def __init__(self, impersonate: str = "chrome", delay: float = 0.15):
        self.impersonate = impersonate
        self.delay = delay
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def get_category_paths(self, session: Any) -> List[Dict[str, str]]:
        """Extrae la ruta jerárquica exacta de VTEX (/1/12/95/) para cada categoría"""
        resp = session.get(CATEGORY_TREE_URL)
        if resp.status != 200:
            return []
        tree = resp.json()

        paths = []
        def walk(nodes, current_path=""):
            for node in nodes:
                node_id = str(node["id"])
                path = f"{current_path}/{node_id}"
                children = node.get("children", [])
                if not children:
                    paths.append({"path": f"{path}/", "name": node["name"]})
                else:
                    walk(children, path)

        walk(tree)
        return paths

    def scrape_all(self, batch_size: int = 50):
        start_time = time.time()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando extracción COMPLETA de La Sirena...")

        products_map: Dict[str, Dict[str, Any]] = {}
        processed_paths: Set[str] = set()

        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, "r", encoding="utf-8") as pf:
                    saved_prog = json.load(pf)
                    products_map = saved_prog.get("products", {})
                    processed_paths = set(saved_prog.get("processed_paths", []))
                    print(f"Reanudando progreso: {len(products_map)} productos ya guardados de {len(processed_paths)} subcategorías.")
            except Exception as e:
                print(f"Iniciando progreso desde cero ({e}).")

        with FetcherSession(impersonate=self.impersonate, stealthy_headers=True) as session:
            cat_list = self.get_category_paths(session)
            total_cats = len(cat_list)
            print(f"Total subcategorías válidas encontradas: {total_cats}")

            for idx, cat in enumerate(cat_list, 1):
                cat_path = cat["path"]
                cat_name = cat["name"]

                if cat_path in processed_paths:
                    continue

                offset = 0

                while True:
                    limit = offset + batch_size - 1
                    url = f"{SEARCH_URL}?_from={offset}&_to={limit}&fq=C:{cat_path}"

                    try:
                        resp = session.get(url)
                    except Exception as e:
                        time.sleep(1)
                        continue

                    if resp.status not in (200, 206):
                        break

                    try:
                        items = resp.json()
                    except Exception:
                        break

                    if not items or len(items) == 0:
                        break

                    for raw in items:
                        p_id = str(raw.get("productId"))
                        if p_id in products_map:
                            continue

                        skus = raw.get("items", [])
                        first_sku = skus[0] if skus else {}
                        sellers = first_sku.get("sellers", [])
                        comm_offer = sellers[0].get("commertialOffer", {}) if sellers else {}
                        images = first_sku.get("images", [])

                        products_map[p_id] = {
                            "id": p_id,
                            "name": raw.get("productName"),
                            "brand": raw.get("brand"),
                            "link": raw.get("link"),
                            "categories": raw.get("categories", []),
                            "price": comm_offer.get("Price"),
                            "list_price": comm_offer.get("ListPrice"),
                            "available": comm_offer.get("AvailableQuantity", 0) > 0,
                            "available_quantity": comm_offer.get("AvailableQuantity", 0),
                            "image_url": images[0].get("imageUrl") if images else None,
                            "scraped_at": datetime.now(timezone.utc).isoformat()
                        }

                    offset += batch_size
                    if len(items) < batch_size:
                        break

                    time.sleep(self.delay)

                processed_paths.add(cat_path)

                if idx % 15 == 0 or idx == total_cats:
                    elapsed = time.time() - start_time
                    print(f"[{idx}/{total_cats}] cats | {len(products_map)} productos únicos extraídos | Tiempo: {int(elapsed//60)}m {int(elapsed%60)}s")
                    
                    with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
                        json.dump({
                            "products": products_map,
                            "processed_paths": list(processed_paths)
                        }, pf)

        total_elapsed = time.time() - start_time
        mins = int(total_elapsed // 60)
        secs = int(total_elapsed % 60)

        final_list = list(products_map.values())
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "store": "La Sirena (sirena.do)",
                "total_products": len(final_list),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(total_elapsed, 2),
                "duration_formatted": f"{mins} minutos y {secs} segundos",
                "products": final_list
            }, f, ensure_ascii=False, indent=2)

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

        print(f"\n==========================================")
        print(f"✓ EXTRACCIÓN TOTAL FINALIZADA")
        print(f"Total productos únicos: {len(final_list)}")
        print(f"Tiempo total: {mins} minutos y {secs} segundos")
        print(f"Guardado en: {OUTPUT_FILE.resolve()}")
        print(f"==========================================")

if __name__ == "__main__":
    scraper = FullSirenaScraper(delay=0.15)
    scraper.scrape_all()
