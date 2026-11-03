import urllib.request
import urllib.parse
import http.cookiejar
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from db import upsert_rate

BCRD_BASE_URL = "https://www.bancentral.gov.do"
BCRD_HISTORICO_PAGE = f"{BCRD_BASE_URL}/SectorExterno/HistoricoTasas"
BCRD_ACTUAL_ENDPOINT = f"{BCRD_BASE_URL}/Home/GetActualExchangeRate"
BCRD_HISTORICO_ENDPOINT = f"{BCRD_BASE_URL}/Home/GetHistoricalExchangeRates"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": BCRD_HISTORICO_PAGE,
    "Origin": BCRD_BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
}

class BCRDScraper:
    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self._initialized = False

    def _ensure_session(self):
        """Visita la página inicial para recibir la cookie de sesión ASP.NET requerida"""
        if not self._initialized:
            req = urllib.request.Request(BCRD_HISTORICO_PAGE, headers=HEADERS)
            with self.opener.open(req, timeout=20) as resp:
                resp.read()
            self._initialized = True

    def fetch_today_rate(self) -> Optional[Dict[str, Any]]:
        """Extrae la tasa del día actual reportada por el Banco Central y la guarda en la BD"""
        self._ensure_session()
        req = urllib.request.Request(
            BCRD_ACTUAL_ENDPOINT,
            data=b"",
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        with self.opener.open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data.get("success") or not data.get("result"):
            return None

        result = data["result"]
        # fecha viene como "2026-11-03T00:00:00Z"
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
        """Extrae el historial de los últimos N días y los guarda en SQLite"""
        self._ensure_session()
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days_back)

        payload = urllib.parse.urlencode({
            "fromDate": from_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "toDate": to_date.strftime("%Y-%m-%dT23:59:59.000Z"),
            "purchaseColumnOrder": "",
            "sellingColumnOrder": "",
            "dateColumnOrder": "desc",
            "isForReporting": "false",
        }).encode("utf-8")

        req = urllib.request.Request(
            BCRD_HISTORICO_ENDPOINT,
            data=payload,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )

        with self.opener.open(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))

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
