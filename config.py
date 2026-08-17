import os

class Config(object):
    # Bot Config
    try:
        API_ID = int(os.environ.get("API_ID", ""))
    except ValueError:
        API_ID = 27891965
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # DB Config
    MONGO_URI = os.environ.get("MONGO_URI", "")
    
    # Bot Ownership
    OWNERS = [int(x) for x in os.environ.get("OWNERS", "").split() if x]
    
    try:
        LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0") or "0")
    except ValueError:
        LOG_CHANNEL = 0
