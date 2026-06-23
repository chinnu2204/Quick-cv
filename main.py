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
try:
    db.add_log("INFO", "SYSTEM_STARTUP", "QuickCV Multi-Bot Orchestrator boot cycle started.")
except Exception as db_err:
    logger.warning(f"Database logging on boot skipped: {db_err}")

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
        "<p>All automated bots are actively running in production long-polling mode.</p>"
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
    logger.info("Initializing multi-bot de-duplicated orchestrator...")
    
    # Track polling status to prevent duplicate loops
    polling_tasks = []
    
    # Clean and parse tokens
    placeholders = {
        "your_user_bot_token_here",
        "your_admin_bot_token_here",
        "your_credit_bot_token_here",
        "",
        None
    }
    
    tokens_map = {
        "UserBot": (USER_BOT_TOKEN or "").strip(),
        "AdminBot": (ADMIN_BOT_TOKEN or "").strip(),
        "CreditBot": (CREDIT_BOT_TOKEN or "").strip(),
    }
    
    # De-duplicate tokens so we compile bots sharing the same token into a single loop
    token_to_roles = {}
    for bot_role, token_val in tokens_map.items():
        if token_val and token_val not in placeholders:
            if token_val not in token_to_roles:
                token_to_roles[token_val] = []
            token_to_roles[token_val].append(bot_role)
            
    # Resolve active Bot clients
    bot_clients = {}
    user_bot_instance = None
    admin_bot_instance = None
    credit_bot_instance = None
    
    for token, roles in token_to_roles.items():
        try:
            bot_client = Bot(token=token)
            me = await bot_client.get_me()
            
            # Print beautiful metadata report
            logger.info("================================================")
            logger.info(f"Bot Name     : {me.full_name}")
            logger.info(f"Bot ID       : {me.id}")
            logger.info(f"Token Status : Valid & Active")
            logger.info(f"Roles Assigned: {', '.join(roles)}")
            logger.info(f"Polling Status: Initializing")
            logger.info("================================================")
            
            # Save client references for internal cross-bot communication
            for r in roles:
                bot_clients[r] = bot_client
                
        except Exception as e:
            logger.critical(f"FATAL: Token validation failed for roles {roles}: {e}")
            
    # Map static instances and fallbacks
    user_bot_instance = bot_clients.get("UserBot")
    admin_bot_instance = bot_clients.get("AdminBot")
    credit_bot_instance = bot_clients.get("CreditBot")
    
    # Inject references safely so modules can cross-communicate
    if admin_bot_instance:
        admin_bot_module.user_bot_shared = user_bot_instance or admin_bot_instance
    if user_bot_instance:
        user_bot_module.credit_bot_shared = credit_bot_instance or user_bot_instance
    if admin_bot_instance:
        admin_bot_module.credit_bot_shared = credit_bot_instance or admin_bot_instance

    # Create dedicated polling instances per unique token
    initialized_services_logs = []
    
    for token, roles in token_to_roles.items():
        # Get primary bot client for this token
        representative_role = roles[0]
        bot_client = bot_clients.get(representative_role)
        if not bot_client:
            continue
            
        # Create dedicated Dispatcher for this loop
        dp = Dispatcher()
        routers_found = []
        
        # Include corresponding routers for all assigned roles sharing this token
        if "UserBot" in roles:
            dp.include_router(user_bot_module.router)
            routers_found.append("User Router")
        if "AdminBot" in roles:
            dp.include_router(admin_bot_module.router)
            routers_found.append("Admin Router")
        if "CreditBot" in roles:
            dp.include_router(credit_bot_module.router)
            routers_found.append("Credit Router")
            
        initialized_services_logs.append(f"{'/'.join(roles)} (Enabled)")
        
        # Define clean separate running task to capture variables correctly
        def make_polling_coro(b_client, b_dp, b_roles, r_list):
            async def run_bot_polling():
                b_name = "Unknown"
                try:
                    me_info = await b_client.get_me()
                    b_name = me_info.full_name
                except Exception:
                    pass
                
                logger.info(f"Starting boot routine for bot: '{b_name}' ({'/'.join(b_roles)}).")
                
                # Infinite loop to manage reconnection + automatic recovery
                while True:
                    try:
                        logger.info(f"Flushing previous webhook session for bot: '{b_name}'...")
                        await b_client.delete_webhook(drop_pending_updates=True)
                        logger.info(f"Cleared webhooks! Starting aiogram polling for bot: '{b_name}' on routers: {', '.join(r_list)}")
                        
                        # Start polling and monitor
                        logger.info(f"Polling Status: Active for '{b_name}' ({'/'.join(b_roles)})")
                        await b_dp.start_polling(b_client, skip_updates=True)
                        
                    except Exception as err:
                        logger.error(f"Polling connection dropped or conflict for bot '{b_name}': {err}.")
                        logger.info("Polling Status: Reconnecting in 10s...")
                        await asyncio.sleep(10)
            return run_bot_polling
            
        polling_tasks.append(make_polling_coro(bot_client, dp, roles, routers_found))

    # Log general startup
    if initialized_services_logs:
        status_msg = f"De-duplicated service pool initialized: {', '.join(initialized_services_logs)}"
        logger.info(status_msg)
        try:
            db.add_log("INFO", "SERVICES_STARTED", status_msg)
        except Exception:
            pass
    else:
        logger.warning("No valid bot services launched. Ensure your tokens env is set correctly.")
        try:
            db.add_log("WARNING", "NO_SERVICES_STARTED", "No valid bot tokens provided. System idling.")
        except Exception:
            pass

    # Start Health keep-alive web-server inside local event loop
    app = init_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Production web health-check server listening actively on port {PORT}.")

    # Launch bots in background tasks (only 1 target per unique token)
    launched_tasks = []
    for poller in polling_tasks:
        launched_tasks.append(asyncio.create_task(poller()))

    logger.info(f"All {len(launched_tasks)} de-duplicated active bot loops successfully launched.")

    # Keep container open and monitor tasks
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Main system orchestrator caught cancellation. Shutting down tasks gracefully...")
        for t in launched_tasks:
            t.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("QuickCV services shutdown completed safely.")
