import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# App Configurations
PORT = int(os.getenv("PORT", 3000))
APP_URL = os.getenv("APP_URL", "")

# Telegram Bot Configurations
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN", "")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
CREDIT_BOT_TOKEN = os.getenv("CREDIT_BOT_TOKEN", "")

# Admin ID parsing
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if ADMIN_IDS_RAW:
    for aid in ADMIN_IDS_RAW.split(","):
        aid = aid.strip()
        if aid.isdigit():
            ADMIN_IDS.append(int(aid))

# OpenCode API Config
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_API_URL = os.getenv("OPENCODE_API_URL", "https://api.opencode.ai/v1/chat/completions")

# Model definitions (Mapping Display Names to technical model tags silently)
SUPPORTED_MODELS = [
    {"display_name": "DeepSeek V4 Flash Free", "model_id": "deepseek-v4-flash-free", "enabled": True},
    {"display_name": "Qwen 3.6 Plus Free", "model_id": "qwen-36-plus-free", "enabled": True},
    {"display_name": "MiniMax M3 Free", "model_id": "minimax-m3-free", "enabled": True},
    {"display_name": "MiMo V2.5 Free", "model_id": "mimo-v25-free", "enabled": True},
    {"display_name": "Nemotron 3 Ultra Free", "model_id": "nemotron-3-ultra-free", "enabled": True},
    {"display_name": "North Mini Code Free", "model_id": "north-mini-code-free", "enabled": True}
]

DEFAULT_MODEL_ID = "deepseek-v4-flash-free"

# Storage paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Check if Render persistent disk volume mount is available
if os.path.exists("/data") and os.path.isdir("/data"):
    DB_PATH = "/data/quickcv.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "database", "quickcv.db")

RESUMES_DIR = os.path.join(BASE_DIR, "generated_resumes")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Ensure folders exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(RESUMES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
