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
from config.generator import call_opencode_api, create_resume_files, call_opencode_api_generic
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

class WebsiteFlow(StatesGroup):
    genre = State()
    topic = State()
    style = State()

class AppFlow(StatesGroup):
    platform = State()
    purpose = State()

class CodeFlow(StatesGroup):
    language = State()
    task = State()

class DesignFlow(StatesGroup):
    asset_type = State()
    prompt_desc = State()

class DocFlow(StatesGroup):
    doc_type = State()
    details = State()

class CareerFlow(StatesGroup):
    tool_type = State()
    context = State()

# Global reference to notify CreditBot. Will be injected on main.py startup.
credit_bot_shared = None

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Resume Builder"), KeyboardButton(text="🌐 Website Builder")],
            [KeyboardButton(text="📱 App Builder"), KeyboardButton(text="💻 Code Generator")],
            [KeyboardButton(text="🎨 Design Generator"), KeyboardButton(text="📑 Documents")],
            [KeyboardButton(text="💼 Career Tools"), KeyboardButton(text="👤 Profile")],
            [KeyboardButton(text="🎁 Daily Reward"), KeyboardButton(text="👥 Referral Program")],
            [KeyboardButton(text="📂 My Projects"), KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Select a feature from the main menu:"
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
    
    main_buttons = [
        "📄 Resume Builder", "🌐 Website Builder", "📱 App Builder", "💻 Code Generator",
        "🎨 Design Generator", "📑 Documents", "💼 Career Tools", "👤 Profile",
        "🎁 Daily Reward", "👥 Referral Program", "📂 My Projects", "⚙️ Settings", "❌ Cancel"
    ]
    
    if text.startswith("/") or text in main_buttons:
        await state.clear()
        if text.startswith("/start"):
            await cmd_start(message, state)
        elif text.startswith("/cancel") or text == "❌ Cancel":
            await cmd_cancel(message, state)
        elif text == "📄 Resume Builder":
            await start_resume_flow(message, state)
        elif text == "🌐 Website Builder":
            await start_website_flow(message, state)
        elif text == "📱 App Builder":
            await start_app_flow(message, state)
        elif text == "💻 Code Generator":
            await start_code_flow(message, state)
        elif text == "🎨 Design Generator":
            await start_design_flow(message, state)
        elif text == "📑 Documents":
            await start_doc_flow(message, state)
        elif text == "💼 Career Tools":
            await start_career_flow(message, state)
        elif text == "👤 Profile":
            await show_profile(message)
        elif text == "🎁 Daily Reward":
            await claim_reward(message)
        elif text == "👥 Referral Program":
            await refer_friends(message)
        elif text == "📂 My Projects":
            await view_my_projects(message)
        elif text == "⚙️ Settings":
            await show_settings(message)
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
        [InlineKeyboardButton(text="🎯 ATS Friendly Resume", callback_data="prof_ats"),
         InlineKeyboardButton(text="✨ Modern Resume", callback_data="prof_modern")],
        [InlineKeyboardButton(text="💼 Professional Resume", callback_data="prof_professional"),
         InlineKeyboardButton(text="🌱 Fresher Resume", callback_data="prof_fresher")],
        [InlineKeyboardButton(text="📈 Experienced Resume", callback_data="prof_experienced"),
         InlineKeyboardButton(text="💻 Developer Resume", callback_data="prof_developer")],
        [InlineKeyboardButton(text="🎨 Designer Resume", callback_data="prof_designer"),
         InlineKeyboardButton(text="🍎 Teacher Resume", callback_data="prof_teacher")],
        [InlineKeyboardButton(text="🛡️ Security Guard Resume", callback_data="prof_security"),
         InlineKeyboardButton(text="🤖 Custom AI Resume", callback_data="prof_custom")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    
    await message.answer(
        "📝 **QuickCV Profession Selection**\n\n"
        "Please select a template style or custom profession to begin tailoring your resume:\n\n"
        "1. 🎯 **ATS Friendly Resume** (Optimized structure)\n"
        "2. ✨ **Modern Resume** (Stylish & crisp)\n"
        "3. 💼 **Professional Resume** (Corporate focus)\n"
        "4. 🌱 **Fresher Resume** (Academics & highlights)\n"
        "5. 📈 **Experienced Resume** (Leader focus)\n"
        "6. 💻 **Developer Resume** (Tech-fast track! Auto skill populating)\n"
        "7. 🎨 **Designer Resume** (Creative portfolio highlights)\n"
        "8. 🍎 **Teacher Resume** (Education & certification focus)\n"
        "9. 🛡️ **Security Guard Resume** (Trust & vigilance layout)\n"
        "10. 🤖 **Custom AI Resume** (Any roles/ideas freeform)",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@router.callback_query(ResumeFlow.profession, F.data.startswith("prof_"))
async def process_profession_callback(callback: CallbackQuery, state: FSMContext):
    choice = callback.data
    
    prof_map = {
        "prof_ats": "ATS Friendly Resume",
        "prof_modern": "Modern Resume",
        "prof_professional": "Professional Resume",
        "prof_fresher": "Fresher Resume",
        "prof_experienced": "Experienced Resume",
        "prof_developer": "Developer Resume",
        "prof_designer": "Designer Resume",
        "prof_teacher": "Teacher Resume",
        "prof_security": "Security Guard Resume",
        "prof_custom": "Custom AI Resume"
    }
    
    profession_name = prof_map.get(choice, "Resume Builder")
    await state.update_data(profession=profession_name)
    
    await callback.answer(f"Selected: {profession_name}")
    await callback.message.edit_text(
        f"🎯 **Template Selected:** {profession_name}\n\n"
        "Initializing template parameters..."
    )
    
    is_developer = (choice == "prof_developer" or "developer" in profession_name.lower())
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
    is_developer = (profession == "Developer Resume" or "developer" in profession.lower())
    
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
    is_developer = (profession == "Developer Resume" or "developer" in profession.lower())
    
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
    is_developer = (profession == "Developer Resume" or "developer" in profession.lower())
    
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
    is_developer = (profession == "Developer Resume" or "developer" in profession.lower())
    
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
    is_developer = (profession == "Developer Resume" or "developer" in profession.lower())
    
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

# --- ULTIMATE MULTI-CATEGORY AI BUILDER FLOWS ---

import uuid

# -- 1. WEBSITE BUILDER --

@router.message(F.text == "🌐 Website Builder")
async def start_website_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends under '👥 Referral Program' to gain build credits.", parse_mode="Markdown")
        return
    await state.set_state(WebsiteFlow.genre)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💼 Portfolio Website", callback_data="web_genre_Portfolio Theme"),
         InlineKeyboardButton(text="🏢 Business Platform", callback_data="web_genre_Business Web")],
        [InlineKeyboardButton(text="🎯 Landing Page", callback_data="web_genre_Landing Page"),
         InlineKeyboardButton(text="📌 Personal Blog", callback_data="web_genre_Personal Site")],
        [InlineKeyboardButton(text="🍽️ Restaurant Menu", callback_data="web_genre_Restaurant Board"),
         InlineKeyboardButton(text="🛍️ E-commerce Portal", callback_data="web_genre_E-commerce Web")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("🌐 **Select Website Type/Style** to begin generation:", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(WebsiteFlow.genre, F.data.startswith("web_genre_"))
async def process_website_genre(callback: CallbackQuery, state: FSMContext):
    genre_name = callback.data.split("web_genre_")[-1]
    await state.update_data(genre=genre_name)
    await callback.answer(f"Selected: {genre_name}")
    await state.set_state(WebsiteFlow.topic)
    await callback.message.edit_text(
        f"🌐 **Website Type:** {genre_name}\n\n"
        "🔹 **Next:** Please type the **Topic, Business Name, or Domain theme** of this website:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(WebsiteFlow.topic)
async def state_website_topic(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 2:
        await message.reply("Please input a valid website topic.")
        return
    await state.update_data(topic=message.text.strip())
    await state.set_state(WebsiteFlow.style)
    await message.answer(
        "🔹 **Style Parameters:** Specify any design criteria (e.g., dark cyber theme, warm editorial serif, minimalist grid, products list, custom sections):",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(WebsiteFlow.style)
async def state_website_style(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text:
        await message.reply("Please input style details or type 'None'.")
        return
    await state.update_data(style=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Website creation failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Drafting your custom responsive website... Handshaking AI model...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert Frontend Developer and Designer. Your task is to output a single-file, highly polished "
        "fully responsive HTML page with modern CSS styles and interactive JavaScript scripts. "
        "The design must look professional, clean, responsive, and functional, matching the user's specific guidelines. "
        "CRITICAL BRANDING REQUIREMENT: The webpage footer MUST explicitly contain the text 'Built with QuickCV AI'. "
        "Write raw code only without any prefix chat explanation; output the full HTML document."
    )
    prompt = f"Genre: {data['genre']}\nTopic: {data['topic']}\nStyle details: {data['style']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"{data['genre']} - {data['topic']}"
        db.save_project(message.from_user.id, title, "website", data["genre"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **Website generated successfully with {model_name}!**\n\nFind your complete, fully single-file responsive code assets below:", reply_markup=get_main_keyboard())
        
        try:
            await status_msg.delete()
        except:
            pass

        web_filename = f"website_{message.from_user.id}_{str(uuid.uuid4())[:4]}.html"
        web_path = os.path.join(RESUMES_DIR, web_filename)
        with open(web_path, "w", encoding="utf-8") as f:
            f.write(content)
        await message.reply_document(
            document=FSInputFile(web_path, filename="index.html"),
            caption="🌐 **Your Complete responsive Website HTML File!**\n\nFeatures custom reactive Javascript assets. Feel free to host or preview locally!"
        )
    except Exception as e:
        logger.error(f"Website generation failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- 2. APP BUILDER --

@router.message(F.text == "📱 App Builder")
async def start_app_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends to gain model credits.", parse_mode="Markdown")
        return
    await state.set_state(AppFlow.platform)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Flutter Complete Code", callback_data="app_plat_Flutter Native"),
         InlineKeyboardButton(text="🤖 Android Kotlin Compose", callback_data="app_plat_Android Kotlin")],
        [InlineKeyboardButton(text="🛍️ E-commerce App Template", callback_data="app_plat_E-commerce"),
         InlineKeyboardButton(text="💬 Interactive Chat UI", callback_data="app_plat_Chat App")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("📱 **Select App platform style/framework:**", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(AppFlow.platform, F.data.startswith("app_plat_"))
async def process_app_platform(callback: CallbackQuery, state: FSMContext):
    plat_name = callback.data.split("app_plat_")[-1]
    await state.update_data(platform=plat_name)
    await callback.answer(f"Selected: {plat_name}")
    await state.set_state(AppFlow.purpose)
    await callback.message.edit_text(
        f"📱 **Mobile Platform:** {plat_name}\n\n"
        "🔹 **Next:** Detail the requirements for the mobile app layout and active features to implement under the hood:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(AppFlow.purpose)
async def state_app_purpose(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please input a valid app description.")
        return
    await state.update_data(purpose=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. App creation failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Drafting complete source architecture... Compiling mobile app patterns...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert Mobile Software Engineer. Your task is to output full professional production-level mobile app "
        "code (e.g. Flutter main.dart or Kotlin Compose main layout file) based on user specs. "
        "State and widget components must be completely defined. "
        "CRITICAL BRANDING REQUIREMENT: The application's About/Settings panel MUST explicitly show "
        "the text 'Powered by QuickCV AI' or contain an about modal section referencing it. "
        "Do not write secondary chat explanations; output the clean, compilable code only."
    )
    prompt = f"Platform/Framework Style: {data['platform']}\nApplication Purpose & Workflow Spec: {data['purpose']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"{data['platform']} App"
        db.save_project(message.from_user.id, title, "app", data["platform"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **App Codebase Compiled successfully with {model_name}!**\n\nFind your complete, fully responsive app code assets below:", reply_markup=get_main_keyboard())
        try: await status_msg.delete()
        except: pass

        ext = "dart" if "Flutter" in data["platform"] else "kt"
        filename = f"main_activity_{message.from_user.id}_{str(uuid.uuid4())[:4]}.{ext}"
        app_path = os.path.join(RESUMES_DIR, filename)
        with open(app_path, "w", encoding="utf-8") as f:
            f.write(content)
        await message.reply_document(
            document=FSInputFile(app_path, filename=f"main.{ext}"),
            caption=f"📱 **Your complete main source code file ({data['platform']})!**\n\nAbout section explicitly contains 'Powered by QuickCV AI' attribution."
        )
    except Exception as e:
        logger.error(f"App generation failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- 3. CODE GENERATOR --

@router.message(F.text == "💻 Code Generator")
async def start_code_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends to gain model credits.", parse_mode="Markdown")
        return
    await state.set_state(CodeFlow.language)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐍 Python Scripts", callback_data="code_lang_Python"),
         InlineKeyboardButton(text="🤖 Telegram Bots", callback_data="code_lang_Telegram Bot")],
        [InlineKeyboardButton(text="🔗 Discord Bots / APIs", callback_data="code_lang_Discord and API"),
         InlineKeyboardButton(text="💻 Web Projects", callback_data="code_lang_HTML and CSS")],
        [InlineKeyboardButton(text="⚙️ Automation & Schemas", callback_data="code_lang_Automation and Schema")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("💻 **Select AI Code target template:**", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(CodeFlow.language, F.data.startswith("code_lang_"))
async def process_code_lang(callback: CallbackQuery, state: FSMContext):
    lang_name = callback.data.split("code_lang_")[-1]
    await state.update_data(language=lang_name)
    await callback.answer(f"Selected: {lang_name}")
    await state.set_state(CodeFlow.task)
    await callback.message.edit_text(
        f"💻 **Code Category:** {lang_name}\n\n"
        "🔹 **Next:** Describe the task, features, error context to solve, or automation logic you require the AI to write:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(CodeFlow.task)
async def state_code_task(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please input a valid task prompt.")
        return
    await state.update_data(task=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Code generation failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Writing production-ready executable code...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert Senior Software Engineer. Deliver highly elegant, robust, complete "
        "production-ready executable codes according to user specifications. Include necessary library imports, "
        "robust error handling, and logical inline comments. Write clean, complete files without truncated snippets."
    )
    prompt = f"Category: {data['language']}\nCore task & logic: {data['task']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"{data['language']} script"
        db.save_project(message.from_user.id, title, "code", data["language"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **Code written successfully with {model_name}!**\n\nFind your complete files below:", reply_markup=get_main_keyboard())
        try: await status_msg.delete()
        except: pass

        ext = "py" if "Python" in data["language"] else "txt"
        if "HTML" in data["language"]: ext = "html"
        
        code_fn = f"script_{message.from_user.id}_{str(uuid.uuid4())[:4]}.{ext}"
        code_path = os.path.join(RESUMES_DIR, code_fn)
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        await message.reply_document(
            document=FSInputFile(code_path, filename=code_fn),
            caption=f"💻 **Complete Codebase:** `{data['language']}` layout and logical helpers."
        )
    except Exception as e:
        logger.error(f"Code generation failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- 4. DESIGN GENERATOR --

@router.message(F.text == "🎨 Design Generator")
async def start_design_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends to gain model credits.", parse_mode="Markdown")
        return
    await state.set_state(DesignFlow.asset_type)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Logo / Identity", callback_data="design_type_Logo"),
         InlineKeyboardButton(text="📱 Social Post / Banner", callback_data="design_type_Banner")],
        [InlineKeyboardButton(text="📑 Business Card Layout", callback_data="design_type_Business Card"),
         InlineKeyboardButton(text="🎨 Posters / Thumbnails", callback_data="design_type_Poster")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("🎨 **Choose visual design target:**", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(DesignFlow.asset_type, F.data.startswith("design_type_"))
async def process_design_type(callback: CallbackQuery, state: FSMContext):
    design_type = callback.data.split("design_type_")[-1]
    await state.update_data(asset_type=design_type)
    await callback.answer(f"Selected: {design_type}")
    await state.set_state(DesignFlow.prompt_desc)
    await callback.message.edit_text(
        f"🎨 **Design Target:** {design_type}\n\n"
        "🔹 **Next:** Provide any slogans, theme colors, core design keywords, or custom specifications for the brand asset Layout:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(DesignFlow.prompt_desc)
async def state_design_desc(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text:
        await message.reply("Please input a valid design prompt description.")
        return
    await state.update_data(prompt_desc=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Design generation failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Drafting creative design layouts and styling vectors...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert Graphics and UI/UX Brand Designer. Output an extremely detailed visual spec draft, "
        "complete brand colors (with HEX hex-codes), typography rules, and CSS/SVG styling models for the chosen "
        "asset type. Output clean, visually stunning specs."
    )
    prompt = f"Design Type: {data['asset_type']}\nCreative Guidelines & brand text: {data['prompt_desc']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"{data['asset_type']} spec"
        db.save_project(message.from_user.id, title, "design", data["asset_type"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **Creative Layout generated with {model_name}!**\n\nFind your complete brand specification sheet below:", reply_markup=get_main_keyboard())
        try: await status_msg.delete()
        except: pass
        await message.answer(f"🎨 **{title.upper()} SPECIFICATION**\n\n{content}")
    except Exception as e:
        logger.error(f"Design asset draft failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- 5. DOCUMENTS BUILDER --

@router.message(F.text == "📑 Documents")
async def start_doc_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends to gain model credits.", parse_mode="Markdown")
        return
    await state.set_state(DocFlow.doc_type)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Professional Invoice", callback_data="doc_style_Invoice"),
         InlineKeyboardButton(text="📜 Legal Agreement / Contract", callback_data="doc_style_Agreement")],
        [InlineKeyboardButton(text="📊 Business Proposal", callback_data="doc_style_Proposal"),
         InlineKeyboardButton(text="🎓 Certification / Report", callback_data="doc_style_Report")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("📑 **Select Document draft category:**", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(DocFlow.doc_type, F.data.startswith("doc_style_"))
async def process_doc_style(callback: CallbackQuery, state: FSMContext):
    doc_style = callback.data.split("doc_style_")[-1]
    await state.update_data(doc_type=doc_style)
    await callback.answer(f"Selected: {doc_style}")
    await state.set_state(DocFlow.details)
    await callback.message.edit_text(
        f"📑 **Document Category:** {doc_style}\n\n"
        "🔹 **Next:** Provide the names of parties involved, invoice total amount, dates, terms, and essential clauses to populating the formal document model:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(DocFlow.details)
async def state_doc_details(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text:
        await message.reply("Please input valid document specifications.")
        return
    await state.update_data(details=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Document generation failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Formatting formal templates... Drafting professional legal terms...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert Professional Content Writer and Corporate Secretary. Generate highly professional, "
        "legally coherent, beautifully formatted binding drafts based on user specifications. Do not include informal greeting comments."
    )
    prompt = f"Document Layout: {data['doc_type']}\nDetails: {data['details']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"Draft of {data['doc_type']}"
        db.save_project(message.from_user.id, title, "document", data["doc_type"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **Document drafted successfully with {model_name}!**\n\nFind your complete, print-ready document draft below:", reply_markup=get_main_keyboard())
        try: await status_msg.delete()
        except: pass

        doc_filename = f"document_{message.from_user.id}_{str(uuid.uuid4())[:4]}.txt"
        doc_path = os.path.join(RESUMES_DIR, doc_filename)
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        await message.reply_document(
            document=FSInputFile(doc_path, filename=f"{data['doc_type'].replace(' ', '_')}.txt"),
            caption=f"📑 **Your complete formalized document draft ({data['doc_type']})!**"
        )
    except Exception as e:
        logger.error(f"Document drafting failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- 6. CAREER TOOLS --

@router.message(F.text == "💼 Career Tools")
async def start_career_flow(message: Message, state: FSMContext):
    if db.is_banned(message.from_user.id): return
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await message.answer("❌ **No Credits Remaining**\n\nPlease claim daily rewards or invite friends to gain model credits.", parse_mode="Markdown")
        return
    await state.set_state(CareerFlow.tool_type)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Cover Letter Builder", callback_data="career_cat_Cover Letter Builder"),
         InlineKeyboardButton(text="💬 Interview Trainer Q&As", callback_data="career_cat_Interview Trainer")],
        [InlineKeyboardButton(text="💎 LinkedIn Bio Optimizer", callback_data="career_cat_LinkedIn Bio Optimizer"),
         InlineKeyboardButton(text="📊 Resume Score ATS Checker", callback_data="career_cat_Resume ATS Checker")],
        [InlineKeyboardButton(text="❌ Cancel & Exit", callback_data="cancel_creation")]
    ])
    await message.answer("💼 **Select Career Suitcase Tool:**", reply_markup=markup, parse_mode="Markdown")

@router.callback_query(CareerFlow.tool_type, F.data.startswith("career_cat_"))
async def process_career_cat(callback: CallbackQuery, state: FSMContext):
    cat_style = callback.data.split("career_cat_")[-1]
    await state.update_data(tool_type=cat_style)
    await callback.answer(f"Selected: {cat_style}")
    await state.set_state(CareerFlow.context)
    await callback.message.edit_text(
        f"💼 **Career Tool:** {cat_style}\n\n"
        "🔹 **Next:** Please provide the relevant job role, paste your resume description, or enter candidate details to analyze:",
        reply_markup=get_cancel_markup(),
        parse_mode="Markdown"
    )

@router.message(CareerFlow.context)
async def state_career_val(message: Message, state: FSMContext):
    if await check_intercept_menu(message, state): return
    if not message.text or len(message.text.strip()) < 5:
        await message.reply("Please input a valid prompt query.")
        return
    await state.update_data(context=message.text.strip())
    
    credits_info = db.get_credits(message.from_user.id)
    if credits_info["balance"] < 1 and credits_info["unlimited"] == 0:
        await state.clear()
        await message.answer("❌ Out of credits. Analysis failed.", reply_markup=get_main_keyboard())
        return

    status_msg = await message.answer("⚙️ **Analyzing profile metrics... Crafting strategic coaching recommendation...**")
    data = await state.get_data()
    await state.clear()

    active_model = db.get_active_model()
    model_id = active_model["model_id"]
    model_name = active_model["display_name"]

    system_prompt = (
        "You are an expert HR Manager and Senior Career Recruiter. Deliver elite, high-impact tactical advice, "
        "personalized cover letters, interview trainer guides, or rigorous resume score checks. Deliver professional tactical details."
    )
    prompt = f"Selected Strategic tool: {data['tool_type']}\nUser Data / Context: {data['context']}"

    try:
        content = call_opencode_api_generic(prompt, system_prompt, model_id)
        
        title = f"{data['tool_type']} advice"
        db.save_project(message.from_user.id, title, "career", data["tool_type"], content)
        db.consume_credit(message.from_user.id)

        await message.answer(f"🎉 **Report successfully processed with {model_name}!**\n\nFind your complete career coaching results below:", reply_markup=get_main_keyboard())
        try: await status_msg.delete()
        except: pass
        await message.answer(f"💼 **{data['tool_type'].upper()} REPORT**\n\n{content}")
    except Exception as e:
        logger.error(f"Career tool execution failed: {e}", exc_info=True)
        try: await status_msg.delete()
        except: pass
        await message.answer("⚠️ AI generation temporarily unavailable. Please try again.", reply_markup=get_main_keyboard())

# -- MY PROJECTS WORKSPACE HISTORY --

@router.message(F.text == "📂 My Projects")
async def view_my_projects(message: Message):
    if db.is_banned(message.from_user.id): return
    user_id = message.from_user.id
    resumes = db.get_user_resumes(user_id)
    projects = db.get_user_projects(user_id)
    
    if not resumes and not projects:
        await message.answer(
            "📂 **Your Projects Shelf is Empty!**\n\n"
            "You haven't generated any items yet. Choose one of our options in the main menu to begin crafting websites, apps, code, documents, or resumes!",
            parse_mode="Markdown"
        )
        return
        
    text = (
        "📂 **QuickCV AI Project Workspace**\n\n"
        f"You have `{len(resumes) + len(projects)}` active entries inside your secure cloud space:\n\n"
    )
    
    if resumes:
        text += "📄 **ATS & Profession Resumes:**\n"
        for r in resumes[:5]:
            text += f"• `{r['title']}` ({r['created_at'][:10]})\n"
        if len(resumes) > 5:
            text += "• *...and more (view under Resumes)*\n"
        text += "\n"
        
    if projects:
        text += "🚀 **Generated AI Projects:**\n"
        for p in projects[:10]:
            cat_emoji = {
                "website": "🌐",
                "app": "📱",
                "code": "💻",
                "design": "🎨",
                "document": "📑",
                "career": "💼"
            }.get(p["category"], "⚙️")
            text += f"{cat_emoji} **{p['sub_category']}** - `{p['title']}` ({p['created_at'][:10]})\n"
        if len(projects) > 10:
            text += "• *...and other older creations* \n"
              
    text += "\nRetrieve or view full saved data under individual category lists below:"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Resumes", callback_data="proj_cat_resume"),
            InlineKeyboardButton(text="🌐 Websites & Apps", callback_data="proj_cat_web_app")
        ],
        [
            InlineKeyboardButton(text="💻 AI Codes & Docs", callback_data="proj_cat_code_doc"),
            InlineKeyboardButton(text="🎨 Designs & Career", callback_data="proj_cat_design_career")
        ]
    ])
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@router.message(F.text == "👤 Profile")
async def show_profile(message: Message):
    if db.is_banned(message.from_user.id): return
    user_id = message.from_user.id
    credits_info = db.get_credits(user_id)
    balance = credits_info["balance"]
    is_unlimited = credits_info["unlimited"]
    
    resumes = db.get_user_resumes(user_id)
    projects = db.get_user_projects(user_id)
    
    role = "🥇 Unlimited Creator" if is_unlimited else "🎒 Standard User"
    
    text = (
        "👤 **QuickCV User Profile**\n\n"
        f"• **User ID:** `{user_id}`\n"
        f"• **Category Tier:** {role}\n"
        f"• **Available Credits:** `{ '∞' if is_unlimited else balance }` credits\n\n"
        "📊 **Platform Generation Stats:**\n"
        f"• Total Resumes Created: `{len(resumes)}` docs\n"
        f"• Custom Projects: `{len(projects)}` saved items\n\n"
        "💡 *Claim daily rewards or refer friends under '👥 Referral Program' to boost your balance!*"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "👥 Referral Program")
async def refer_program_btn(message: Message):
    await refer_friends(message)

@router.message(F.text == "⚙️ Settings")
async def show_settings(message: Message):
    if db.is_banned(message.from_user.id): return
    active_model = db.get_active_model()
    text = (
        "⚙️ **QuickCV Platform Settings**\n\n"
        f"⚡ **Active AI Generation Model:**\n`{active_model['display_name']}` ({active_model['model_id']})\n\n"
        "🎨 *Output Rules Applied:*\n"
        "• PDF/Word Resumes: No Watermarks, fully ATS-compliant.\n"
        "• Responsive Websites: Clean styling, with 'Built with QuickCV AI' footer.\n"
        "• Mobile Applications: Packaged framework source with 'Powered by QuickCV AI' About sections.\n"
        "• Clean code outputs with complete structure & guides."
    )
    await message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data.startswith("proj_cat_"))
async def process_project_category_callback(callback: CallbackQuery):
    cat_id = callback.data.split("proj_cat_")[-1]
    user_id = callback.from_user.id
    
    if cat_id == "resume":
        resumes = db.get_user_resumes(user_id)
        if not resumes:
            await callback.answer("No resumes generated yet!", show_alert=True)
            return
        await callback.message.answer("📄 **Your Saved Resumes:**")
        for r in resumes[:10]:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📥 Download PDF", callback_data=f"down_pdf_{r['id']}"),
                    InlineKeyboardButton(text="📥 Download DOCX", callback_data=f"down_docx_{r['id']}")
                ],
                [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"del_cv_{r['id']}")]
            ])
            await callback.message.answer(f"📄 **{r['title']}**\n📅 {r['created_at'][:10]}", reply_markup=markup)
        await callback.answer("Listed Resumes.")
        
    elif cat_id == "web_app":
        projects = db.get_user_projects(user_id)
        web_apps = [p for p in projects if p["category"] in ["website", "app"]]
        if not web_apps:
            await callback.answer("No websites or app codebases generated yet!", show_alert=True)
            return
        
        await callback.message.answer("🌐📱 **Your Generated Websites & Apps:**")
        for p in web_apps[:10]:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁️ View Code Summary", callback_data=f"proj_show_{p['id']}")]
            ])
            await callback.message.answer(f"📦 **{p['sub_category']}** - `{p['title']}`\n📅 {p['created_at'][:10]}", reply_markup=markup)
        await callback.answer("Listed web and app templates.")
        
    elif cat_id == "code_doc":
        projects = db.get_user_projects(user_id)
        code_docs = [p for p in projects if p["category"] in ["code", "document"]]
        if not code_docs:
            await callback.answer("No codes or documents generated yet!", show_alert=True)
            return
        
        await callback.message.answer("💻📑 **Your Generated Codes & Documents:**")
        for p in code_docs[:10]:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁️ Download/View source", callback_data=f"proj_show_{p['id']}")]
            ])
            await callback.message.answer(f"⚙️ **{p['sub_category']}** - `{p['title']}`\n📅 {p['created_at'][:10]}", reply_markup=markup)
        await callback.answer("Listed codes.")
        
    elif cat_id == "design_career":
        projects = db.get_user_projects(user_id)
        design_careers = [p for p in projects if p["category"] in ["design", "career"]]
        if not design_careers:
            await callback.answer("No designs or career reports generated yet!", show_alert=True)
            return
        
        await callback.message.answer("🎨💼 **Your Generated Designs & Reports:**")
        for p in design_careers[:10]:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁️ View Details", callback_data=f"proj_show_{p['id']}")]
            ])
            await callback.message.answer(f"✨ **{p['sub_category']}** - `{p['title']}`\n📅 {p['created_at'][:10]}", reply_markup=markup)
        await callback.answer("Listed layouts.")

@router.callback_query(F.data.startswith("proj_show_"))
async def process_show_project_callback(callback: CallbackQuery):
    proj_id = callback.data.split("proj_show_")[-1]
    
    try:
        def _get_p(conn):
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (proj_id,)).fetchone()
            return dict(row) if row else None
        p = db._run_with_retry(_get_p)
    except Exception as d_err:
        logger.error(f"Callback error fetching project: {d_err}")
        await callback.answer("⚠️ Database busy. Please try again.", show_alert=True)
        return
        
    if not p:
        await callback.answer("Project not found.", show_alert=True)
        return
        
    if p["user_id"] != callback.from_user.id:
        await callback.answer("Access Denied: You do not own this project.", show_alert=True)
        return
        
    await callback.answer("Loading project assets...")
    
    cat = p["category"]
    ext = {
        "website": "html",
        "app": "dart" if "Flutter" in p["sub_category"] else "kt",
        "code": "py" if "Python" in p["sub_category"] else "html" if "HTML" in p["sub_category"] else "txt",
        "design": "txt",
        "document": "txt",
        "career": "txt"
    }.get(cat, "txt")
    
    sub = p["sub_category"].replace(" ", "_")
    fn = f"retrieve_{sub}_{p['id']}.{ext}"
    p_path = os.path.join(RESUMES_DIR, fn)
    with open(p_path, "w", encoding="utf-8") as f:
        f.write(p["content"])
        
    await callback.message.answer(f"📂 **Retrieving active resource block: `{p['title']}` ({p['sub_category']})**")
    try:
        await callback.message.reply_document(
            document=FSInputFile(p_path, filename=fn),
            caption=f"🚀 **Full source content saved on QuickCV platform.**"
        )
    except Exception as tr_err:
        logger.error(f"Error transferring project document callback: {tr_err}")
        await callback.message.answer("⚠️ Failed to transfer codebase source. Please try re-requesting.")
