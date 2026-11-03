import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from db import init_db, get_latest_rate, get_rate_by_date, get_rates_history
from scraper import BCRDScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

scraper = BCRDScraper()
scheduler = BackgroundScheduler()

def scheduled_job():
    """Tarea que ejecuta el cron diario"""
    logger.info("Executing scheduled dollar rate sync...")
    try:
        rate = scraper.fetch_today_rate()
        logger.info(f"Rate sync success: {rate}")
    except Exception as e:
        logger.error(f"Error during rate sync: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar Base de Datos
    init_db()
    
    # Sincronización inicial al levantar el servicio
    try:
        logger.info("Executing startup sync...")
        scraper.fetch_today_rate()
        scraper.fetch_historical_rates(days_back=15)
    except Exception as e:
        logger.warning(f"Startup sync failed: {e}")

    # Configurar Cron diario:
    # Por defecto a las 9:00 AM y 5:00 PM hora local de República Dominicana (America/Santo_Domingo)
    scheduler.add_job(
        scheduled_job,
        CronTrigger(hour="9,17", minute="0", timezone="America/Santo_Domingo"),
        id="daily_rate_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started successfully (Cron: 09:00 & 17:00 AST).")

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped.")

app = FastAPI(
    title="Dollar Rate Scraper API (Dominican Republic)",
    description="Microservicio con Scrapling para consultar la tasa oficial del dólar (BCRD / DGII) con Cron integrado",
    version="1.0.0",
    lifespan=lifespan
)

# Permitir CORS para que tu otra app (React, Vue, Flutter, Next.js, etc.) pueda consultar la API directamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "dollar-rate-api",
        "docs": "/docs",
        "endpoints": [
            "/api/rates/latest",
            "/api/rates/history",
            "/api/rates/{date}",
            "/api/rates/sync"
        ]
    }

@app.get("/api/rates/latest")
def latest_rate(currency: str = Query(default="USD", description="Moneda: USD o EUR")):
    """Retorna la última tasa de cambio disponible en la base de datos"""
    rate = get_latest_rate(currency=currency.upper())
    if not rate:
        # Si aún no hay en BD, intentamos consultar en vivo
        try:
            live = scraper.fetch_today_rate()
            if live:
                return live
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="No exchange rate available yet.")
    return rate

@app.get("/api/rates/history")
def history_rates(
    from_date: Optional[str] = Query(default=None, description="Fecha de inicio (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(default=None, description="Fecha de fin (YYYY-MM-DD)"),
    limit: int = Query(default=30, le=365, description="Máximo número de registros")
):
    """Retorna el historial de tasas guardadas"""
    return get_rates_history(from_date=from_date, to_date=to_date, limit=limit)

@app.get("/api/rates/{date}")
def rate_by_date(date: str, currency: str = Query(default="USD")):
    """Retorna la tasa de una fecha específica en formato YYYY-MM-DD (ej. 2026-11-03)"""
    rate = get_rate_by_date(date, currency=currency.upper())
    if not rate:
        raise HTTPException(status_code=404, detail=f"No rate found for date {date}")
    return rate

@app.post("/api/rates/sync")
def force_sync():
    """Fuerza una actualización inmediata contra el Banco Central"""
    try:
        today = scraper.fetch_today_rate()
        history = scraper.fetch_historical_rates(days_back=7)
        return {
            "status": "success",
            "synced_today": today,
            "historical_items_updated": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
