import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from database.db_manager import DBManager

# Loading configurations
from config.settings import (
    USER_BOT_TOKEN, ADMIN_BOT_TOKEN, CREDIT_BOT_TOKEN, PORT
)

# Route handlers / routers
import bots.user_bot as user_bot_module
import bots.credit_bot as credit_bot_module
import admin.admin_bot as admin_bot_module

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("QuickCVMain")

# 1. Initialize SQLite Database
db = DBManager()
db.add_log("INFO", "SYSTEM_STARTUP", "QuickCV Multi-Bot Orchestrator boot cycle started.")

# 2. Setup Health Check Web Server
async def handle_ping_request(request):
    html_response = (
        "<html>"
        "<head>"
        "<title>QuickCV Bot Server</title>"
        "<style>"
        "body { font-family: -apple-system, system-ui, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }"
        "h1 { color: #38bdf8; margin-bottom: 8px; }"
        "p { color: #94a3b8; font-size: 1.1em; margin-top: 0; }"
        "div.badge { background: #1e293b; border: 1px solid #334155; padding: 12px 24px; border-radius: 8px; margin-top: 15px; }"
        "</style>"
        "</head>"
        "<body>"
        "<h1>⚡ QuickCV Telegram SaaS</h1>"
        "<p>All 3 automated bots are actively running in production long-polling mode.</p>"
        "<div class='badge'>User Bot Router | Admin Bot Console | Credit Monitor</div>"
        "</body>"
        "</html>"
    )
    return web.Response(text=html_response, content_type="text/html")

def init_web_app():
    app = web.Application()
    app.router.add_get("/", handle_ping_request)
    app.router.add_get("/healthz", lambda r: web.Response(text="OK"))
    return app

# 3. Main Multi-Bot Coroutine Orchestrator
async def main():
    runners = []
    
    # Track which bots initialized successfully
    initialized_bots = []
    
    # Dispatcher instances
    user_dp = Dispatcher()
    admin_dp = Dispatcher()
    credit_dp = Dispatcher()
    
    # Register blueprints (routers)
    user_dp.include_router(user_bot_module.router)
    admin_dp.include_router(admin_bot_module.router)
    credit_dp.include_router(credit_bot_module.router)

    # Validate and initialize User Bot
    user_bot_instance = None
    if USER_BOT_TOKEN and USER_BOT_TOKEN != "your_user_bot_token_here":
        try:
            user_bot_instance = Bot(token=USER_BOT_TOKEN)
            # Inject dependency into static references
            admin_bot_module.user_bot_shared = user_bot_instance
            
            async def start_user_polling():
                logger.info("Starting QuickCV User Bot polling loop...")
                while True:
                    try:
                        await user_dp.start_polling(user_bot_instance)
                    except Exception as err:
                        logger.error(f"User Bot polling encountered an error: {err}. Re-establishing in 10s...")
                        await asyncio.sleep(10)
            runners.append(start_user_polling)
            initialized_bots.append("UserBot (Active)")
        except Exception as e:
            logger.error(f"Failed to load User Bot instance: {str(e)}")
    else:
        logger.warning("USER_BOT_TOKEN environment variable not set or contains default placeholder.")

    # Validate and initialize Admin Bot
    admin_bot_instance = None
    if ADMIN_BOT_TOKEN and ADMIN_BOT_TOKEN != "your_admin_bot_token_here":
        try:
            admin_bot_instance = Bot(token=ADMIN_BOT_TOKEN)
            async def start_admin_polling():
                logger.info("Starting QuickCV Admin Panel Bot polling loop...")
                while True:
                    try:
                        await admin_dp.start_polling(admin_bot_instance)
                    except Exception as err:
                        logger.error(f"Admin Bot polling encountered an error: {err}. Re-establishing in 10s...")
                        await asyncio.sleep(10)
            runners.append(start_admin_polling)
            initialized_bots.append("AdminBot (Active)")
        except Exception as e:
            logger.error(f"Failed to load Admin Bot instance: {str(e)}")
    else:
        logger.warning("ADMIN_BOT_TOKEN environment variable not set or contains default placeholder.")

    # Validate and initialize Credit Bot
    credit_bot_instance = None
    if CREDIT_BOT_TOKEN and CREDIT_BOT_TOKEN != "your_credit_bot_token_here":
        try:
            credit_bot_instance = Bot(token=CREDIT_BOT_TOKEN)
            # Inject dependency references so the other modules can message notification alerts
            user_bot_module.credit_bot_shared = credit_bot_instance
            admin_bot_module.credit_bot_shared = credit_bot_instance
            
            async def start_credit_polling():
                logger.info("Starting QuickCV Credit & Notification Bot polling loop...")
                while True:
                    try:
                        await credit_dp.start_polling(credit_bot_instance)
                    except Exception as err:
                        logger.error(f"Credit Bot polling encountered an error: {err}. Re-establishing in 10s...")
                        await asyncio.sleep(10)
            runners.append(start_credit_polling)
            initialized_bots.append("CreditBot (Active)")
        except Exception as e:
            logger.error(f"Failed to load Credit Bot instance: {str(e)}")
    else:
        logger.warning("CREDIT_BOT_TOKEN environment variable not set or contains default placeholder.")

    # Log operational report
    if initialized_bots:
        logger.info(f"System loaded successfully with active services: {', '.join(initialized_bots)}")
        db.add_log("INFO", "SERVICES_STARTED", f"Running: {', '.join(initialized_bots)}")
    else:
        logger.warning("No Telegram bots were loaded. To activate, specify token variables in your environment or .env file.")
        db.add_log("WARNING", "NO_SERVICES_STARTED", "No bots loaded. Enter tokens in secrets config to use.")

    # Start Health keep-alive web-server inside local event loop
    app = init_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Port health listener initialized successfully on port {PORT}.")

    # Launch bots in background tasks
    launched_tasks = []
    for task in runners:
        launched_tasks.append(asyncio.create_task(task()))

    logger.info("All initialized background bot tasks launched.")

    # Keep the main loop alive forever so webserver and bots stay up
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Main worker canceled.")
        # Clean up background tasks
        for t in launched_tasks:
            t.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("QuickCV runner shutdown finished.")
