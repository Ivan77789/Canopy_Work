import os

from dotenv import load_dotenv

load_dotenv()

WALLET_PASSWORD = os.getenv("WALLET_PASSWORD", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Ежедневные квесты (faucet и т.п.) сбрасываются в 00:00 UTC — если включено,
# скрипт перед стартом обхода профилей дожидается этого момента.
WAIT_FOR_UTC_MIDNIGHT = os.getenv("WAIT_FOR_UTC_MIDNIGHT", "false").lower() == "true"
