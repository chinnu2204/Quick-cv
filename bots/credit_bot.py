import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from database.db_manager import DBManager

router = Router()
db = DBManager()

@router.message(Command("start"))
async def start_credit_bot(message: Message):
    # Standard registration check
    user = db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or ""
    )
    
    welcome_text = (
        "⚡ **Welcome to QuickCV Credit Alerts Channel!** ⚡\n\n"
        "I am your automated transaction notifier. Keeping me active guarantees that "
        "you get notified instant-time on balance shifts:\n\n"
        "🎁 **Reward payouts**\n"
        "🎉 **Referrals join confirmations**\n"
        "⚡ **Bonus deposits by administrators**\n\n"
        "No further action is required here, I will message you automatically!"
    )
    await message.answer(welcome_text, parse_mode="Markdown")
