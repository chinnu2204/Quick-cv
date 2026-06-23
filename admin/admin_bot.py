import os
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db_manager import DBManager

router = Router()
db = DBManager()

# Admin FSM States
class AdminFlow(StatesGroup):
    broadcast_msg = State()
    search_user = State()
    modify_credits_user = State()
    ban_user_id = State()
    unban_user_id = State()

# Global reference to both other bots so we can dispatch notifications if needed on credits/broadcasts.
user_bot_shared = None
credit_bot_shared = None

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 System Dashboard"), KeyboardButton(text="⚙️ Switch AI Model")],
            [KeyboardButton(text="👥 Search / Manage Users"), KeyboardButton(text="📢 Broadcast Bulletin")],
            [KeyboardButton(text="📜 Telemetry Logs"), KeyboardButton(text="ℹ️ Panel Commands")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Admin Operation Dashboard:"
    )

# Middleware check replacement
def is_request_from_admin(message: Message) -> bool:
    return db.is_admin(message.from_user.id)

@router.message(Command("start"))
async def cmd_admin_start(message: Message, state: FSMContext):
    await state.clear()
    if not is_request_from_admin(message):
        await message.reply("🔒 **Request Denied**: This bot is only accessible to white-listed administrators.")
        return

    welcome = (
        "👑 **Welcome to Python QuickCV Super Admin Panel!**\n\n"
        "You have full direct control over users, credits distribution, active AI engine models, and global alerts broadcasting right inside this conversation."
    )
    await message.answer(welcome, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

@router.message(Command("dashboard"))
@router.message(F.text == "📊 System Dashboard")
async def show_dashboard(message: Message):
    if not is_request_from_admin(message): return
    
    stats = db.get_dashboard_stats()
    active_m = db.get_active_model()
    
    dash_text = (
        "📊 **QuickCV System Metrics Dashboard**\n\n"
        f"• **Total Registered Users:** `{stats['total_users']}`\n"
        f"• **Active Credit Profiles:** `{stats['active_users']}`\n"
        f"• **New Registrations Today:** `{stats['todays_users']}`\n\n"
        f"• **Total Resumes Generated:** `{stats['total_resumes']}`\n"
        f"• **Resumes Created Today:** `{stats['todays_resumes']}`\n\n"
        f"• **System Credits Rendered:** `{stats['credits_used']}` generations\n"
        f"• **Total Active Credits Floating:** `{stats['credits_remaining']}`\n"
        f"• **Current Active AI Engine:** `{active_m['display_name']}`\n"
    )
    await message.answer(dash_text, parse_mode="Markdown")

# --- AI MODEL MANAGEMENT ---

@router.message(Command("models"))
@router.message(F.text == "⚙️ Switch AI Model")
async def show_models_panel(message: Message):
    if not is_request_from_admin(message): return
    
    models = db.get_models()
    active_m = db.get_active_model()
    
    text = (
        "⚙️ **QuickCV AI Engine Orchestration**\n\n"
        "Select the default model utilized to structure ATS-friendly output resumes. "
        "Any switch applies instantly with no backend restart requirements.\n\n"
        f"👉 **Current Selected:** `{active_m['display_name']}`\n"
    )
    
    keyboard_buttons = []
    for m in models:
        prefix = "✅ " if m["model_id"] == active_m["model_id"] else ""
        button_text = f"{prefix}{m['display_name']}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"set_model_{m['model_id']}")])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith("set_model_"))
async def callback_set_model(callback: CallbackQuery):
    if not db.is_admin(callback.from_user.id):
        await callback.answer("Permission Denied.")
        return
        
    model_id = callback.data.replace("set_model_", "")
    models = db.get_models()
    selected_model_name = ""
    
    # Enable Model validation
    for m in models:
        if m["model_id"] == model_id:
            m["enabled"] = True
            selected_model_name = m["display_name"]
            
    db.set_setting("active_model_id", model_id)
    db.add_log("ADMIN_ACTION", "MODEL_CHANGED", f"AI generation model updated to: {selected_model_name}", callback.from_user.id)
    
    await callback.answer(f"Success: Active model set to {selected_model_name}!")
    
    # Re-render list
    models = db.get_models()
    keyboard_buttons = []
    for m in models:
        prefix = "✅ " if m["model_id"] == model_id else ""
        keyboard_buttons.append([InlineKeyboardButton(text=f"{prefix}{m['display_name']}", callback_data=f"set_model_{m['model_id']}")])
        
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(
        f"⚙️ **QuickCV AI Engine Orchestration**\n\nModel switched successfully!\n\n👉 **Current Selected:** `{selected_model_name}`\n",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# --- TELEMETRY LOGS ---

@router.message(Command("logs"))
@router.message(F.text == "📜 Telemetry Logs")
async def view_recent_logs(message: Message):
    if not is_request_from_admin(message): return
    
    logs = db.get_logs(limit=15)
    if not logs:
        await message.answer("📜 Logs database empty currently.")
        return
        
    text = "📜 **Recent Telemetry Audit Logs (Last 15)**\n\n"
    for l in logs:
        # shorten timestamp
        t = l['timestamp'][11:19]
        text += f"`[{t}]` **{l['category']}**: {l['message']} *(ID: {l['user_id'] or 'SYS'})*\n"
        
    await message.answer(text, parse_mode="Markdown")

# --- BROADCAST SYSTEM ---

@router.message(Command("broadcast"))
@router.message(F.text == "📢 Broadcast Bulletin")
async def start_broadcast(message: Message, state: FSMContext):
    if not is_request_from_admin(message): return
    
    await state.set_state(AdminFlow.broadcast_msg)
    await message.answer(
        "📢 **Global Announcement Creator**\n\n"
        "Send me the message (text) you want to broadcast to ALL registered users.\n\n"
        "Type /cancel to close out.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Cancel")]], resize_keyboard=True)
    )

@router.message(AdminFlow.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_request_from_admin(message): return
    if message.text == "❌ Cancel" or message.text == "/cancel":
        await state.clear()
        await message.answer("Broadcast canceled.", reply_markup=get_admin_keyboard())
        return

    broadcast_text = message.text
    await state.clear()
    
    status_msg = await message.answer("⚡ **Dispersing bulletin now. Please standby...**")
    
    # Fetch all users from SQLite (everyone registered)
    users = db.get_all_users_for_admin()
    
    sent = 0
    delivered = 0
    failed = 0
    
    for u in users:
        user_id = u["id"]
        sent += 1
        try:
            # We must use user_bot_shared to broadcast
            if user_bot_shared:
                await user_bot_shared.send_message(chat_id=user_id, text=broadcast_text)
                delivered += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            
    db.add_log("ADMIN_ACTION", "BROADCAST_COMPLETED", f"Broadcast finished. Sent={sent}, Delivered={delivered}, Failed={failed}", message.from_user.id)
    
    report = (
        "📢 **Global Broadcast Dispersal Report**\n\n"
        f"• **Sent attempts:** `{sent}`\n"
        f"• **Delivered:** `{delivered}`\n"
        f"• **Failed / Blocked:** `{failed}`"
    )
    
    await status_msg.delete()
    await message.answer(report, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

# --- USER MANAGEMENT ---

@router.message(Command("users"))
@router.message(F.text == "👥 Search / Manage Users")
async def request_user_search(message: Message, state: FSMContext):
    if not is_request_from_admin(message): return
    
    await state.set_state(AdminFlow.search_user)
    await message.answer(
        "🔎 **User Directory Search Console**\n\n"
        "Enter username, first/last name, or raw Telegram ID to inspect:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Cancel")]], resize_keyboard=True)
    )

@router.message(AdminFlow.search_user)
async def cmd_process_search(message: Message, state: FSMContext):
    if not is_request_from_admin(message): return
    if message.text == "❌ Cancel" or message.text == "/cancel":
        await state.clear()
        await message.answer("Search exited.", reply_markup=get_admin_keyboard())
        return
        
    query = message.text.strip()
    await state.clear()
    
    results = db.search_user_by_query(query)
    
    if not results:
        await message.answer(f"🔍 No results found for query: `{query}`", reply_markup=get_admin_keyboard(), parse_mode="Markdown")
        return
        
    await message.answer(f"🔍 **Search Matches Found ({len(results)}):**", reply_markup=get_admin_keyboard())
    
    for u in results[:8]: # Restrict visual listing
        user_id = u["id"]
        cred = u["balance"] or 0
        unl = u["unlimited"] or 0
        ban = u["is_banned"] or 0
        joined = u["joined_at"][:10]
        
        status_line = "🔴 Suspended" if ban else "🟢 Active"
        unlim_tag = " [🏆 Unlimited]" if unl else ""
        
        caption = (
            f"👤 **{u['first_name']} {u['last_name'] or ''}**\n"
            f"• Username: @{u['username'] or 'None'}\n"
            f"• Telegram ID: `{user_id}`\n"
            f"• Status: {status_line}\n"
            f"• Balance: `{cred}` credits{unlim_tag}\n"
            f"• Date Joined: {joined}"
        )
        
        # Build interactive actions keyboard
        btns = [
            [
                InlineKeyboardButton(text="➕ Grant +5 Cr", callback_data=f"usr_cred_{user_id}_5"),
                InlineKeyboardButton(text="➖ Deduct -5 Cr", callback_data=f"usr_cred_{user_id}_-5")
            ],
            [
                InlineKeyboardButton(text="🏆 Set Unlimited", callback_data=f"usr_cred_{user_id}_unl"),
                InlineKeyboardButton(text="♻️ Reset Balance", callback_data=f"usr_cred_{user_id}_reset")
            ],
            [
                InlineKeyboardButton(text="⛔ Ban User", callback_data=f"usr_ban_{user_id}") if not ban else InlineKeyboardButton(text="🧼 Unban User", callback_data=f"usr_unban_{user_id}"),
                InlineKeyboardButton(text="🗑️ Delete Account", callback_data=f"usr_purge_{user_id}")
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=btns)
        await message.answer(caption, reply_markup=markup, parse_mode="Markdown")

# --- CONSOLE MANAGEMENT CALLBACK HANDLERS ---

@router.callback_query(F.data.startswith("usr_cred_"))
async def callback_adjust_credits(callback: CallbackQuery):
    if not db.is_admin(callback.from_user.id): return
    
    # Syntax: usr_cred_USERID_ACTION
    parts = callback.data.split("_")
    target_id = int(parts[2])
    action = parts[3]
    
    if action == "unl":
        db.modify_credits(target_id, 0, set_unlimited=True)
        # Notify user using CreditBot if available
        if credit_bot_shared:
            try:
                await credit_bot_shared.send_message(
                    chat_id=target_id,
                    text="🏆 **Unlimited Access Awarded!**\n\nAn administrator has granted your account **UNLIMITED Credits**! Enjoy generating as many CVs as you need!"
                )
            except:
                pass
        await callback.answer("Granted unlimited premium balance!", show_alert=True)
    elif action == "reset":
        # reset to standard 2 credits
        db.modify_credits(target_id, 0, set_unlimited=False)
        # Reset balance to exactly 2 with retry-safe db wrapper
        def _reset_balance(conn):
            conn.execute("UPDATE credits SET balance = 2 WHERE user_id = ?", (target_id,))
        db._run_with_retry(_reset_balance)
        await callback.answer("Reset user balance to 2 credits.", show_alert=True)
    else:
        amt = int(action)
        db.modify_credits(target_id, amt)
        if credit_bot_shared:
            try:
                await credit_bot_shared.send_message(
                    chat_id=target_id,
                    text=f"⚡ **Bonus Reward Active!**\n\nAn administrator awarded your account `{amt:+}` Credits!"
                )
            except:
                pass
        await callback.answer(f"Adjusted credits by: {amt:+}", show_alert=True)
        
    # Refresh screen
    await callback.message.delete()

@router.callback_query(F.data.startswith("usr_ban_"))
async def callback_ban_user(callback: CallbackQuery):
    if not db.is_admin(callback.from_user.id): return
    target_id = int(callback.data.split("_")[-1])
    
    db.ban_user(target_id, "Banned by Admin via Command Control Panel.")
    await callback.answer("User profile suspended successfully.", show_alert=True)
    await callback.message.delete()

@router.callback_query(F.data.startswith("usr_unban_"))
async def callback_unban_user(callback: CallbackQuery):
    if not db.is_admin(callback.from_user.id): return
    target_id = int(callback.data.split("_")[-1])
    
    db.unban_user(target_id)
    await callback.answer("User profile restriction removed successfully.", show_alert=True)
    await callback.message.delete()

@router.callback_query(F.data.startswith("usr_purge_"))
async def callback_purge_user(callback: CallbackQuery):
    if not db.is_admin(callback.from_user.id): return
    target_id = int(callback.data.split("_")[-1])
    
    db.delete_user_all_data(target_id)
    await callback.answer("User record fully deleted from system db.", show_alert=True)
    await callback.message.delete()

# --- ADMIN INFO PAGE ---

@router.message(Command("stats"))
@router.message(Command("credits"))
@router.message(Command("ban"))
@router.message(Command("unban"))
@router.message(F.text == "ℹ️ Panel Commands")
async def show_command_documentation(message: Message):
    if not is_request_from_admin(message): return
    help_doc = (
        "👑 **Keyboard Command Cheat-Sheet**\n\n"
        "• `/dashboard` - Overview general user/traffic statistics.\n"
        "• `/models` - Switch active resume generator engines instantly.\n"
        "• `/broadcast` - Dispatch text messages out to all clients.\n"
        "• `/users` - Search, manage permissions, and add/remove credits.\n"
        "• `/logs` - Output latest system developer action metrics.\n"
    )
    await message.answer(help_doc, parse_mode="Markdown")
