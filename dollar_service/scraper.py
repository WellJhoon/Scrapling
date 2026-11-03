import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# Importamos directamente el FetcherSession y Adaptor nativos de tu fork de Scrapling
from scrapling.fetchers import FetcherSession
from db import upsert_rate

BCRD_BASE_URL = "https://www.bancentral.gov.do"
BCRD_HISTORICO_PAGE = f"{BCRD_BASE_URL}/SectorExterno/HistoricoTasas"
BCRD_ACTUAL_ENDPOINT = f"{BCRD_BASE_URL}/Home/GetActualExchangeRate"
BCRD_HISTORICO_ENDPOINT = f"{BCRD_BASE_URL}/Home/GetHistoricalExchangeRates"

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BCRD_HISTORICO_PAGE,
    "Origin": BCRD_BASE_URL,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

class BCRDScraper:
    """
    Scraper oficial del Banco Central de la República Dominicana
    construido sobre el framework Scrapling (FetcherSession con suplantación de huella Chrome).
    """

    def __init__(self, browser_impersonate: str = "chrome"):
        # Scrapling impersonate emula navegadores reales (huellas TLS, headers y cookies dinámicas)
        self.browser_impersonate = browser_impersonate

    def fetch_today_rate(self) -> Optional[Dict[str, Any]]:
        """
        Extrae la tasa oficial del día actual mediante una sesión de Scrapling.
        Almacena el resultado en SQLite.
        """
        with FetcherSession(impersonate=self.browser_impersonate, stealthy_headers=True) as session:
            # 1. Scrapling visita la página inicial y adquiere la sesión ASP.NET
            session.get(BCRD_HISTORICO_PAGE)

            # 2. Petición POST autenticada por la sesión para la tasa actual
            response = session.post(
                BCRD_ACTUAL_ENDPOINT,
                data="",
                headers=AJAX_HEADERS
            )

            if response.status != 200:
                return None

            data = response.json()
            if not data.get("success") or not data.get("result"):
                return None

            result = data["result"]
            raw_date = result.get("date", "")
            date_str = raw_date.split("T")[0] if raw_date else datetime.utcnow().strftime("%Y-%m-%d")

            purchase_rate = float(result.get("actualPurchaseValue", 0.0))
            selling_rate = float(result.get("actualSellingValue", 0.0))
            purchase_delta = float(result.get("actualPurchaseInteranualValue", 0.0))
            selling_delta = float(result.get("actualSellingInteranualValue", 0.0))

            upsert_rate(
                date_str=date_str,
                purchase_rate=purchase_rate,
                selling_rate=selling_rate,
                source="BCRD",
                currency="USD",
                purchase_delta_interanual=purchase_delta,
                selling_delta_interanual=selling_delta,
            )

            return {
                "date": date_str,
                "currency": "USD",
                "source": "BCRD",
                "purchase_rate": purchase_rate,
                "selling_rate": selling_rate,
                "purchase_delta_interanual": purchase_delta,
                "selling_delta_interanual": selling_delta
            }

    def fetch_historical_rates(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """
        Extrae el histórico de tasas del BCRD de los últimos N días usando Scrapling.
        """
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days_back)

        payload = {
            "fromDate": from_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "toDate": to_date.strftime("%Y-%m-%dT23:59:59.000Z"),
            "purchaseColumnOrder": "",
            "sellingColumnOrder": "",
            "dateColumnOrder": "desc",
            "isForReporting": "false",
        }

        with FetcherSession(impersonate=self.browser_impersonate, stealthy_headers=True) as session:
            # Sesión base
            session.get(BCRD_HISTORICO_PAGE)

            response = session.post(
                BCRD_HISTORICO_ENDPOINT,
                data=payload,
                headers=AJAX_HEADERS
            )

            if response.status != 200:
                return []

            data = response.json()
            if not data.get("result") or "items" not in data["result"]:
                return []

            saved_items = []
            for item in data["result"]["items"]:
                raw_date = item.get("date", "")
                date_str = raw_date.split("T")[0]
                purchase_rate = float(item.get("purchaseValue", 0.0))
                selling_rate = float(item.get("sellingValue", 0.0))
                purchase_delta = float(item.get("purchaseInteranualValue", 0.0))
                selling_delta = float(item.get("sellingInteranualValue", 0.0))

                upsert_rate(
                    date_str=date_str,
                    purchase_rate=purchase_rate,
                    selling_rate=selling_rate,
                    source="BCRD",
                    currency="USD",
                    purchase_delta_interanual=purchase_delta,
                    selling_delta_interanual=selling_delta,
                )
                saved_items.append({
                    "date": date_str,
                    "purchase_rate": purchase_rate,
                    "selling_rate": selling_rate
                })

            return saved_items
