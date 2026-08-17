import os

class Config(object):
    # Bot Config
    try:
        API_ID = int(os.environ.get("API_ID", "27891965"))
    except ValueError:
        API_ID = 27891965
    API_HASH = os.environ.get("API_HASH", "909e944f30752b2c47804cbccb8c5c4f")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8116459430:AAHI-gS0XuJLYB4yUSXKghPr4hTsli1QeqQ")
    
    # DB Config
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://thaimozhi2005_db_user:5mcLsi3ySzfhkW3X@autouploader.5dwgbv1.mongodb.net/?appName=AutoUploader")
    
    # Bot Ownership
    OWNERS = [int(x) for x in os.environ.get("OWNERS", "6146353175").split() if x]
    
    # Other config
    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1002926842858")) # For errors/success logs
