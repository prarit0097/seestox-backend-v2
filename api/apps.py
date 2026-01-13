import logging
import os

from django.apps import AppConfig
from threading import Thread
from core_engine.news_fetcher import get_market_news

logger = logging.getLogger("django")

class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        from core_engine.scheduler import start_scheduler
        logger.info("ApiConfig ready: starting scheduler and market news")
        Thread(target=get_market_news, args=("MARKET",), daemon=True).start()
        start_scheduler()

class BackendConfig(AppConfig):
    name = "backend"

    def ready(self):
        from core_engine.price_engine import start_price_engine
        start_price_engine()
