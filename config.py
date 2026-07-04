import os

from dotenv import load_dotenv

load_dotenv()

WALLET_PASSWORD = os.getenv("WALLET_PASSWORD", "")
