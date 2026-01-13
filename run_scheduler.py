import time
import logging

from core_engine.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    start_scheduler()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
