import os
import uuid
import datetime
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db_manager import DBManager
from config.generator import call_opencode_api, create_resume_files
from config.settings import RESUMES_DIR

logger = logging.getLogger("UserBot")
router = Router()
db = DBManager()

class ResumeFlow(StatesGroup):
    profession = State()
    full_name = State()
    phone_number = State()
    email = State()
    address = State()
    objective = State()
    skills = State()
    education = State()
    experience = State()
    projects = State()
    certifications = State()
    languages = State()
    hobbies = State()

# Global reference to notify CreditBot. Will be injected on main.py startup.
credit_bot_shared = None

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Create Resume"), KeyboardButton(text="📂 My Resumes")],
            [KeyboardButton(text="💳 My Credits"), KeyboardButton(text="🎁 Daily Reward")],
            [KeyboardButton(text="👥 Refer Friends"), KeyboardButton(text="📜 Resume History")],
            [KeyboardButton(text="ℹ️ Help")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Select a feature from the menu:"
    )

def get_cancel_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])

# Helper to dispatch notification using credit bot
async def notify_via_credit_bot(user_id, text):
    if credit_bot_shared:
        try:
            await credit_bot_shared.send_message(chat_id=user_id, text=text)
        except Exception as e:
            # Silent fallback if user hasn't started the credit bot
            db.add_log("WARNING", "CREDIT_BOT_NOTIFICATION_FAILED", f"Could not notify user {user_id} via CreditBot: {str(e)}", user_id)

async def check_intercept_menu(message: Message, state: FSMContext) -> bool:
    if not message.text:
        return False
    text = message.text.strip()
    if text.startswith("/") or text in ["📝 Create Resume", "📂 My Resumes", "💳 My Credits", "🎁 Daily Reward", "👥 Refer Friends", "📜 Resume History", "ℹ️ Help", "❌ Cancel"]:
        await state.clear()
        if text.startswith("/start"):
            await cmd_start(message, state)
        elif text.startswith("/cancel") or text == "❌ Cancel":
            await cmd_cancel(message, state)
        elif text == "📝 Create Resume":
            await start_resume_flow(message, state)
        elif text in ["📂 My Resumes", "📜 Resume History"]:
            await view_resumes(message)
        elif text == "💳 My Credits":
            await show_credits(message)
        elif text == "🎁 Daily Reward":
            await claim_reward(message)
        elif text == "👥 Refer Friends":
            await refer_friends(message)
        elif text == "ℹ️ Help":
            await show_help(message)
        return True
    return False

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        logger.warning("[START_RECEIVED] Empty from_user structure in start command.")
        return

    logger.info(f"[START_RECEIVED] /start received from user_id={user_id} message_text='{message.text}'")
    db.add_log("INFO", "START_RECEIVED", f"/start received from {user_id}", user_id)

    try:
        # Step 1: Cleanup FSM wizards
        await state.clear()

        # Step 2: Handle deep linking referral
        ref_referrer_id = None
        args = message.text.split(maxsplit=1) if message.text else []
        if len(args) > 1:
            ref_code = args[1].upper().strip()
            logger.info(f"[USER_LOOKUP] Locating referral owner code='{ref_code}' for user_id={user_id}")
            try:
                referrer = db.get_user_by_referral_code(ref_code)
                if referrer:
                    ref_referrer_id = referrer["id"]
                    logger.info(f"[USER_LOOKUP] Referrer {ref_referrer_id} discovered for user_id={user_id}")
                else:
                    logger.info(f"[USER_LOOKUP] Invalid reference code '{ref_code}' for user_id={user_id}")
            except Exception as rex:
                logger.error(f"[USER_LOOKUP] Referral code lookup failed: {rex}")
                db.add_log("ERROR", "REFERRAL_LOOKUP_FAILED", f"Error querying code: {rex}", user_id)

        # Step 3: Register / Retrieve profile in SQLite database
        first_name = message.from_user.first_name or "User"
        last_name = message.from_user.last_name or ""
        username = message.from_user.username or ""

        logger.info(f"[USER_CREATED] Database profile update initiated for user_id={user_id}")
        try:
            user = db.get_or_create_user(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                referred_by=ref_referrer_id
            )
            logger.info(f"[USER_CREATED] Resolved user database record successfully inside start handler.")
        except Exception as uex:
            logger.error(f"[USER_CREATED] DB user creation failed for user_id={user_id}: {uex}")
            db.add_log("ERROR", "USER_DATABASE_CREATION_FAILED", f"Database create fail: {uex}", user_id)
            raise uex

        # Verify ban check safely
        try:
            banned = db.is_banned(user_id)
        except Exception as bex:
            logger.error(f"Ban check query failed: {bex}")
            banned = False

        if banned:
            logger.warning(f"Banned user_id={user_id} attempted access. Terminated.")
            await message.reply("Access Revoked: Your account is suspended. Please contact support.")
            return

        # Step 4: Referral rewards notification via helper bots
        if ref_referrer_id:
            logger.info(f"[REFERRAL_PROCESSED] Processing referral bonus. referrer={ref_referrer_id}, referee={user_id}")
            try:
                ref_user_name = user.get("first_name", first_name)
                # Strip markdown special formatting from name to be safe
                safe_ref_name = ref_user_name.replace("*", "").replace("_", "").replace("`", "")
                await notify_via_credit_bot(
                    ref_referrer_id, 
                    f"🎉 **Referral Reward Approved!**\n\n+{safe_ref_name} joined QuickCV under your code. **+1 Credit** has been added to your profile!"
                )
                logger.info(f"[REFERRAL_PROCESSED] Sent invite bonus notice successfully to referrer={ref_referrer_id}")
            except Exception as nex:
                logger.warning(f"[REFERRAL_PROCESSED] Non-blocking referral notification failed: {nex}")

        # Step 5: Welcome message output
        safe_first_name = first_name.replace("*", "").replace("_", "").replace("`", "")
        welcome_text = (
            f"👋 Welcome to **QuickCV**, {safe_first_name}!\n\n"
            "Need a professional, ATS-optimized CV but don't know where to start? "
            "We've got you covered! Fill out simple details, and our premium tailored AI writes "
            "and forms a high-impact resume in PDF and DOCX formats instantly.\n\n"
            "💎 **New User Bonus:** You have been credited **2 Free Credits**!"
        )
        
        if ref_referrer_id:
            welcome_text += "\n\n🎉 *Registered via unique invitation link!*"

        logger.info(f"[WELCOME_SENT] Sending primary menu payload to user_id={user_id}")
        await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        logger.info(f"[WELCOME_SENT] Output welcome text successfully inside chat_id={user_id}")
        db.add_log("INFO", "WELCOME_SENT", "Successfully rendered start welcome text.", user_id)

    except Exception as general_err:
        logger.critical(f"UNHANDLED ERROR inside cmd_start handler: {general_err}", exc_info=True)
        try:
            db.add_log("CRITICAL", "START_HANDLER_FAILED", f"Critical handler error: {general_err}", user_id)
        except:
            pass
        # Reliable fallback response
        try:
            await message.answer("⚠️ An internal error occurred. Please try again.", reply_markup=get_main_keyboard())
        except Exception as fex:
            logger.critical(f"Could not output starting fallback to chat {user_id}: {fex}")

@router.message(Command("cancel"))
@router.message(F.text == "❌ Cancel")
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("No active wizard to cancel.", reply_markup=get_main_keyboard())
        return
    await state.clear()
    await message.answer("Creation wizard canceled. Returning to main menu.", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "cancel_creation")
async def inline_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Wizard canceled.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Creation canceled. Back on main dashboard.", reply_markup=get_main_keyboard())

# --- BUTTON MENU DISPATCHING ---

@router.message(F.text == "💳 My Credits")
async def show_credits(message: Message):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    balance = credits_info["balance"]
    is_unlimited = credits_info["unlimited"]
    
    text = (
        "💳 **QuickCV Credits Dashboard**\n\n"
        f"• Status: {'🥇 Unlimited Premium' if is_unlimited else '🎒 Standard Plan'}\n"
        f"• Remaining Balance: `{ '∞' if is_unlimited else balance }` credits\n\n"
        "📌 *Generating 1 custom ATS-friendly CV costs exactly 1 credit.*\n"
        "Claim daily rewards or invite contacts to gain further balance!"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🎁 Daily Reward")
async def claim_reward(message: Message):
    if db.is_banned(message.from_user.id): return
    success, return_text, cooldown = db.claim_daily_reward(message.from_user.id)
    
    if success:
        # Send credit notification via Credit Bot
        await notify_via_credit_bot(
            message.from_user.id,
            "🎁 **Daily Reward Added!**\n\n+2 Credits Added To Your Account. Enjoy generating premium resumes!"
        )
        await message.answer(return_text, reply_markup=get_main_keyboard())
    else:
        # Convert seconds to hours & minutes remaining
        hrs = cooldown // 3600
        mins = (cooldown % 3600) // 60
        await message.answer(
            f"⏳ **Daily Cooldown Active**\n\nYou've already claimed your daily reward today. Please wait `{hrs}h {mins}m` before claiming again.",
            parse_mode="Markdown"
        )

@router.message(F.text == "👥 Refer Friends")
async def refer_friends(message: Message):
    if db.is_banned(message.from_user.id): return
    user = db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or ""
    )
    
    ref_code = user["referral_code"]
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={ref_code}"
    
    text = (
        "👥 **QuickCV Referral Programme**\n\n"
        "Share the gift of automated resume building! For every friend who signs up using your unique link, "
        "your profile instantly receives **+1 Free Credit**.\n\n"
        "🔗 **Your Direct Referral Link:**\n"
        f"`{ref_link}`\n\n"
        "Press to copy the link above and start racking up rewards!"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "ℹ️ Help")
async def show_help(message: Message):
    if db.is_banned(message.from_user.id): return
    help_text = (
        "ℹ️ **QuickCV Help & Documentation**\n\n"
        "QuickCV is your custom virtual Resume Architect. Follow these key steps:\n\n"
        "1️⃣ Press **📝 Create Resume** to start collecting details.\n"
        "2️⃣ Fill each question meticulously. Enter '/cancel' if you wish to exit.\n"
        "3️⃣ We feed it directly into our active AI Generation Engine configured by administrators.\n"
        "4️⃣ Receive editable PDF & DOCX layouts within seconds.\n\n"
        "💡 **Credit Rules:**\n"
        "• 1 Generation = 1 Credit.\n"
        "• 2 credits added on every 24-hour reward system.\n"
        "• Referral invite yields 1 credit on signup.\n\n"
        "For business concerns, reach out to an administrator!"
    )
    await message.answer(help_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.message(F.text == "📂 My Resumes")
@router.message(F.text == "📜 Resume History")
async def view_resumes(message: Message):
    if db.is_banned(message.from_user.id): return
    resumes = db.get_user_resumes(message.from_user.id)
    if not resumes:
        await message.answer("📂 No generated resumes found! Click **📝 Create Resume** to generate your first document.")
        return
        
    await message.answer(f"📜 **Your Generated Resumes ({len(resumes)})**\n\nSelect a file below to redownload custom formats:")
    
    for r in resumes[:10]: # Limit keyboard list feedback to last 10
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 Download PDF", callback_data=f"down_pdf_{r['id']}"),
                InlineKeyboardButton(text="📥 Download DOCX", callback_data=f"down_docx_{r['id']}")
            ],
            [
                InlineKeyboardButton(text="🗑️ Delete record", callback_data=f"del_cv_{r['id']}")
            ]
        ])
        cv_title = r['title'] or f"CV {r['id']}"
        date_str = r['created_at'][:10]
        await message.answer(f"📄 **{cv_title}**\n📅 Created: {date_str}", reply_markup=markup, parse_mode="Markdown")

# --- CONVERSATIONAL RESUME FLOW ---

@router.message(F.text == "📝 Create Resume")
async def start_resume_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer(
            "❌ **No Credits Remaining**\n\nYour current credit balance is **0**. "
            "Please claim your daily reward or invite friends using **👥 Refer Friends** to claim more credits.",
            parse_mode="Markdown"
        )
        return

    await state.set_state(ResumeFlow.profession)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Resume Builder", callback_data="prof_builder")],
        [InlineKeyboardButton(text="📱 Mobile App Developer Resume", callback_data="prof_mobile")],
        [InlineKeyboardButton(text="💻 Website Developer Resume", callback_data="prof_web")],
        [InlineKeyboardButton(text="🌐 Full Stack Developer Resume", callback_data="prof_fullstack")],
        [InlineKeyboardButton(text="🛡️ Security Guard Resume", callback_data="prof_security")],
        [InlineKeyboardButton(text="🧹 Housekeeping Resume", callback_data="prof_housekeeping")],
        [InlineKeyboardButton(text="🤖 Custom AI Resume", callback_data="prof_custom")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    
    await message.answer(
        "📝 **QuickCV Profession Selection**\n\n"
        "Please select a profession/template style to begin tailoring your resume:\n\n"
        "1. **Resume Builder** (Standard Custom)\n"
        "2. **Mobile App Developer Resume** (Pre-optimized)\n"
        "3. **Website Developer Resume** (Pre-optimized)\n"
        "4. **Full Stack Developer Resume** (Pre-optimized)\n"
        "5. **Security Guard Resume** (Tailored layout)\n"
        "6. **Housekeeping Resume** (Tailored layout)\n"
        "7. **Custom AI Resume** (Describe custom role)",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@router.callback_query(ResumeFlow.profession, F.data.startswith("prof_"))
async def process_profession_callback(callback: CallbackQuery, state: FSMContext):
    choice = callback.data
    
    prof_map = {
        "prof_builder": "Resume Builder",
        "prof_mobile": "Mobile App Developer Resume",
        "prof_web": "Website Developer Resume",
        "prof_fullstack": "Full Stack Developer Resume",
        "prof_security": "Security Guard Resume",
        "prof_housekeeping": "Housekeeping Resume",
        "prof_custom": "Custom AI Resume"
    }
    
    profession_name = prof_map.get(choice, "Resume Builder")
    await state.update_data(profession=profession_name)
    
    await callback.answer(f"Selected: {profession_name}")
    await callback.message.edit_text(
        f"🎯 **Profession Selected:** {profession_name}\n\n"
        "Initializing template parameters..."
    )
    
    is_developer = choice in ["prof_mobile", "prof_web", "prof_fullstack"]
    if is_developer:
        await callback.message.answer(
            "⚡ **Developer Template Active!**\n"
            "Your technical skills & project details will be automatically populated with professional "
            "industry standards (React, Flutter, Firebase, etc.). We will skip those questions to optimize your time."
        )
        
    await state.set_state(ResumeFlow.full_name)
    await callback.message.answer(
        "🔹 **Question 1:** What is your **Full Name**?",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(ResumeFlow.full_name)
async def state_name(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 3:
        await message.reply("Please input a valid Full Name.")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(ResumeFlow.phone_number)
    await message.answer("🔹 **Question 2:** Enter your **Phone Number** (including area code):", reply_markup=get_cancel_markup())

@router.message(ResumeFlow.phone_number)
async def state_phone(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 4:
        await message.reply("Please input a valid Phone Number.")
        return
    await state.update_data(phone=message.text.strip())
    await state.set_state(ResumeFlow.email)
    await message.answer("🔹 **Question 3:** What is your **Email Address**?", reply_markup=get_cancel_markup())

@router.message(ResumeFlow.email)
async def state_email(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or "@" not in message.text:
        await message.reply("Please input a valid email address containing '@'.")
        return
    await state.update_data(email=message.text.strip())
    await state.set_state(ResumeFlow.address)
    await message.answer("🔹 **Question 4:** What is your location **Address** (e.g. City, Country)?", reply_markup=get_cancel_markup())

@router.message(ResumeFlow.address)
async def state_address(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 3:
        await message.reply("Please enter an address location.")
        return
    await state.update_data(address=message.text.strip())
    await state.set_state(ResumeFlow.objective)
    await message.answer(
        "🔹 **Question 5:** What is your professional **Career Objective or Summary**?\n\n"
        "Example: *Ambitious software engineer with 3+ years experience looking to build scalable microservices...*",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.objective)
async def state_objective(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 10:
        await message.reply("Please enter a short professional summary or career objective (minimum 10 characters).")
        return
    await state.update_data(objective=message.text.strip())
    
    # Check if this is a developer template
    data = await state.get_data()
    profession = data.get("profession", "")
    is_developer = profession in ["Mobile App Developer Resume", "Website Developer Resume", "Full Stack Developer Resume"]
    
    if is_developer:
        dev_skills = "HTML, CSS, JavaScript, Python, Flutter, React, Firebase, API Integration, UI/UX Design, Database Management"
        await state.update_data(skills=dev_skills)
        await state.set_state(ResumeFlow.education)
        await message.answer(
            "🔹 **Question 6:** Detail your **Education Profile** (Degrees, Institutions, Completion dates):\n\n"
            "Example: *B.Sc. in Computer Science - Boston University (2018 - 2022)*",
            reply_markup=get_cancel_markup()
        )
    else:
        await state.set_state(ResumeFlow.skills)
        await message.answer(
            "🔹 **Question 6:** Enter your key **Professional & Tech Skills** (comma-separated if possible):\n\n"
            "Example: *Python, Django, AWS, React, Agile, SQL*",
            reply_markup=get_cancel_markup()
        )

@router.message(ResumeFlow.skills)
async def state_skills(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 3:
        await message.reply("Please enter at least a few skills.")
        return
    await state.update_data(skills=message.text.strip())
    await state.set_state(ResumeFlow.education)
    await message.answer(
        "🔹 **Question 7:** Detail your **Education Profile** (Degrees, Institutions, Completion dates):\n\n"
        "Example: *B.Sc. in Computer Science - Boston University (2018 - 2022)*",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.education)
async def state_education(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please provide valid education history.")
        return
    await state.update_data(education=message.text.strip())
    
    data = await state.get_data()
    profession = data.get("profession", "")
    is_developer = profession in ["Mobile App Developer Resume", "Website Developer Resume", "Full Stack Developer Resume"]
    
    q_num = "7" if is_developer else "8"
    await state.set_state(ResumeFlow.experience)
    await message.answer(
        f"🔹 **Question {q_num}:** Detail your **Professional Work Experience** (Companies, Roles, and key Achievements):\n\n"
        "Example: *Senior Frontend Developer at Tech Corp (2022 - Present) - Lead team of 4 engineers...*",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.experience)
async def state_experience(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please fill in some work experience.")
        return
    await state.update_data(experience=message.text.strip())
    
    data = await state.get_data()
    profession = data.get("profession", "")
    is_developer = profession in ["Mobile App Developer Resume", "Website Developer Resume", "Full Stack Developer Resume"]
    
    if is_developer:
        dev_projects = "Projects:\n- Mobile Application Development\n- Website Development\n- Telegram Bot Development\n- AI Tools Integration"
        await state.update_data(projects=dev_projects)
        await state.set_state(ResumeFlow.certifications)
        await message.answer(
            "🔹 **Question 8:** What **Professional Certifications** do you possess?\n\n"
            "Example: *AWS Certified Solutions Architect, Scrum Alliance Scrum Master*",
            reply_markup=get_cancel_markup()
        )
    else:
        await state.set_state(ResumeFlow.projects)
        await message.answer(
            "🔹 **Question 9:** Outline your notable **Key Projects** (Title and short description):\n\n"
            "Example: *E-commerce App: Built a full stack shop using Next.js processing $20k monthly transactions...*",
            reply_markup=get_cancel_markup()
        )

@router.message(ResumeFlow.projects)
async def state_projects(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please provide details of at least one project.")
        return
    await state.update_data(projects=message.text.strip())
    await state.set_state(ResumeFlow.certifications)
    await message.answer(
        "🔹 **Question 10:** What **Professional Certifications** do you possess?\n\n"
        "Example: *AWS Certified Solutions Architect, Scrum Alliance Scrum Master*",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.certifications)
async def state_certifications(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text:
         await message.reply("Please input certifications, or type 'None'.")
         return
    await state.update_data(certifications=message.text.strip())
    
    data = await state.get_data()
    profession = data.get("profession", "")
    is_developer = profession in ["Mobile App Developer Resume", "Website Developer Resume", "Full Stack Developer Resume"]
    
    q_num = "9" if is_developer else "11"
    await state.set_state(ResumeFlow.languages)
    await message.answer(
        f"🔹 **Question {q_num}:** What **Languages** do you speak?\n\n"
        "Example: *English (Native), German (Fluent), Spanish (Basic)*",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.languages)
async def state_languages(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 2:
        await message.reply("Please specify languages.")
        return
    await state.update_data(languages=message.text.strip())
    
    data = await state.get_data()
    profession = data.get("profession", "")
    is_developer = profession in ["Mobile App Developer Resume", "Website Developer Resume", "Full Stack Developer Resume"]
    
    q_num = "10" if is_developer else "12"
    await state.set_state(ResumeFlow.hobbies)
    await message.answer(
        f"🔹 **Question {q_num}:** Mention any other **Hobbies or Personal Interests**:",
        reply_markup=get_cancel_markup()
    )

@router.message(ResumeFlow.hobbies)
async def state_hobbies(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text:
         await message.reply("Please input hobbies or type 'None'.")
         return
    
    await state.update_data(hobbies=message.text.strip())
    
    # Check credits once more to avoid edge-cases
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Resume creation failed.", reply_markup=get_main_keyboard())
        return
        
    await message.answer("⚙️ **Drafting complete! Requesting compilation...**", reply_markup=get_main_keyboard())
    
    # State data retrieval
    data = await state.get_data()
    await state.clear()
    
    # ONLY SHOWING THIS TO USERS AS MANDATED BY THE RULES:
    status_msg = await message.answer("⚡ **AI Resume Generation Enabled**")
    
    # Fetch active model
    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]
    
    try:
        # Run GPT compilation
        resume_text = call_opencode_api(data, model_id)
        
        # Compile PDF & DOCX Files
        unique_id = str(uuid.uuid4())[:6]
        pdf_file, docx_file = create_resume_files(message.from_user.id, resume_text, unique_id)
    except Exception as e:
        db.add_log("ERROR", "GENERATION_CRASH", f"Fail: {str(e)}", message.from_user.id)
        try:
            await status_msg.delete()
        except:
            pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())
        return
        
    pdf_full = os.path.join(RESUMES_DIR, pdf_file)
    docx_full = os.path.join(RESUMES_DIR, docx_file)
    
    if not os.path.exists(pdf_full) or not os.path.exists(docx_full):
        try:
            await status_msg.delete()
        except:
            pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())
        return

    # Success! Deduct 1 credit safely now
    db.consume_credit(message.from_user.id)
    
    # Save CV entry in SQLite
    res_title = f"CV of {data.get('name')[:20]}"
    db.save_resume(
        user_id=message.from_user.id,
        title=res_title,
        pdf_path=pdf_file,
        docx_path=docx_file,
        model_used=model_name,
        content=resume_text
    )
    
    # Delete intermediate generation update status
    try:
        await status_msg.delete()
    except:
        pass
        
    # Deliver documents to the client
    await message.answer("🎉 **Resume Generated successfully!**\n\nFind your finalized ATS-optimized copies below:", reply_markup=get_main_keyboard())
    
    if os.path.exists(pdf_full):
        await message.reply_document(
            document=FSInputFile(pdf_full, filename=f"{data.get('name')}_CV.pdf"),
            caption="📄 **Professional PDF Layout (ATS-friendly)**"
        )
    if os.path.exists(docx_full):
        await message.reply_document(
            document=FSInputFile(docx_full, filename=f"{data.get('name')}_CV.docx"),
            caption="📝 **Editable Word Document (.docx)**"
        )

# --- INLINE DOWNLOAD & MANAGING TRIGGERS ---

@router.callback_query(F.data.startswith("down_pdf_"))
async def back_down_pdf(callback: CallbackQuery):
    cv_id = callback.data.split("_")[-1]
    # Fetch resume record with retry-safe db wrapper
    try:
        def _get_pdf(conn):
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (cv_id,)).fetchone()
            return dict(row) if row else None
        row = db._run_with_retry(_get_pdf)
    except Exception as d_err:
        logger.error(f"Callback error fetching PDF resume: {d_err}")
        await callback.answer("⚠️ Database busy. Please try again.", show_alert=True)
        return

    if row:
        if row["user_id"] != callback.from_user.id:
            await callback.answer("Access Denied: You do not own this document.", show_alert=True)
            return
        pdf_path = os.path.join(RESUMES_DIR, row["file_path_pdf"])
        if os.path.exists(pdf_path):
            await callback.answer("Uploading PDF File...")
            try:
                await callback.message.reply_document(
                    document=FSInputFile(pdf_path),
                    caption=f"📄 **Redownloaded [PDF]:** {row['title']}"
                )
            except Exception as tr_err:
                logger.error(f"Failed to deliver PDF document: {tr_err}")
        else:
            await callback.answer("Error: Document file missing on disk.", show_alert=True)
    else:
        await callback.answer("Resume record not found.", show_alert=True)

@router.callback_query(F.data.startswith("down_docx_"))
async def back_down_docx(callback: CallbackQuery):
    cv_id = callback.data.split("_")[-1]
    # Fetch resume record with retry-safe db wrapper
    try:
        def _get_docx(conn):
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (cv_id,)).fetchone()
            return dict(row) if row else None
        row = db._run_with_retry(_get_docx)
    except Exception as d_err:
        logger.error(f"Callback error fetching DOCX resume: {d_err}")
        await callback.answer("⚠️ Database busy. Please try again.", show_alert=True)
        return

    if row:
        if row["user_id"] != callback.from_user.id:
            await callback.answer("Access Denied: You do not own this document.", show_alert=True)
            return
        docx_path = os.path.join(RESUMES_DIR, row["file_path_docx"])
        if os.path.exists(docx_path):
            await callback.answer("Uploading DOCX File...")
            try:
                await callback.message.reply_document(
                    document=FSInputFile(docx_path),
                    caption=f"📝 **Redownloaded [Word DOCX]:** {row['title']}"
                )
            except Exception as tr_err:
                logger.error(f"Failed to deliver DOCX document: {tr_err}")
        else:
            await callback.answer("Error: Document file missing on disk.", show_alert=True)
    else:
        await callback.answer("Resume record not found.", show_alert=True)

@router.callback_query(F.data.startswith("del_cv_"))
async def back_del_cv(callback: CallbackQuery):
    cv_id = callback.data.split("_")[-1]
    
    try:
        def _del_resume(conn):
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (cv_id,)).fetchone()
            if not row:
                return "NOT_FOUND", None
            if row["user_id"] != callback.from_user.id:
                return "DENIED", None
            
            # Perform SQLite deletion
            conn.execute("DELETE FROM resumes WHERE id = ?", (cv_id,))
            return "OK", dict(row)
            
        status, row = db._run_with_retry(_del_resume)
    except Exception as d_err:
        logger.error(f"Callback error deleting resume: {d_err}")
        await callback.answer("⚠️ Database busy. Please try again.", show_alert=True)
        return

    if status == "OK":
        # Delete physical files
        try:
            os.remove(os.path.join(RESUMES_DIR, row["file_path_pdf"]))
            os.remove(os.path.join(RESUMES_DIR, row["file_path_docx"]))
        except:
            pass
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer("Resume document deleted permanently.")
    elif status == "DENIED":
        await callback.answer("Access Denied: You do not own this document.", show_alert=True)
    else:
        await callback.answer("Resume record not found.", show_alert=True)
