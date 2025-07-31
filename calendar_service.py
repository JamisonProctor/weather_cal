import os
from dotenv import load_dotenv
load_dotenv()
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
TOKEN_FILE = os.getenv("TOKEN_FILE")