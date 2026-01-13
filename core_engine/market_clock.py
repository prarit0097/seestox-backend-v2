from datetime import datetime, time

def is_market_open():
    now = datetime.now().time()
    return time(9, 15) <= now <= time(15, 30)
