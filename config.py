import os

from dotenv import load_dotenv

load_dotenv()

WALLET_PASSWORD = os.getenv("WALLET_PASSWORD", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
