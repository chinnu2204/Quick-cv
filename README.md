# ⚡ QuickCV — Multi-Bot Telegram SaaS CV Generator

QuickCV is a 100% Telegram-based AI resume architect SaaS system built with Python 3.11+, Aiogram 3.x, and SQLite. The entire application executes from a unified background service, managing 3 distinct Telegram bots simultaneously that share a common SQLite database and state.

---

## 🏗️ Platform Architecture

QuickCV organizes its features across three distinct bot integrations. All three live inside the same event loop, communicating with the local SQLite persistence engine:

### 🤖 Bot 1: QuickCVBot (User Interface/Panel)
- **Token Env Key:** `USER_BOT_TOKEN`
- **Purpose:** Primary end-user interface. Guided, interactive wizard collecting resume parameters (experience, skills, contact).
- **Core Features:** 12-question conversion wizard, resume PDF/DOCX downloads, credits balance checker, daily reward claimer, and invitation referral marketing link generation.

### 👑 Bot 2: QuickCVPanelBot (Admin Interface/Panel)
- **Token Env Key:** `ADMIN_BOT_TOKEN`
- **Purpose:** Restrictive configuration and metrics module.
- **Core Features:** Real-time logging analytics, user ban/unban controls, manual credit grant bypasses, custom markdown broadcast dispatches, and an on-the-fly LLM model switcher.

### ⚡ Bot 3: QuickCVCreditBot (Transaction Notifier/Channel)
- **Token Env Key:** `CREDIT_BOT_TOKEN`
- **Purpose:** Dedicated webhook transactional notifier channel.
- **Core Features:** Pings the user immediately with beautiful notification plaques upon currency shifts (+2 credits claimed on Daily Rewards, referral signup bonus credits, or manually assigned credits from an admin).

---

## 🛠️ Environmental Variable Configuration

Create a `.env` file in the root folder using our template:

```env
# Telegram Bot API Tokens
USER_BOT_TOKEN="your_user_bot_token"
ADMIN_BOT_TOKEN="your_admin_bot_token"
CREDIT_BOT_TOKEN="your_credit_bot_token"

# OpenCode API Credentials
OPENCODE_API_KEY="your_opencode_api_key"

# Admin Telegram IDs (Comma separated integers)
ADMIN_IDS="123456789,987654321"

# Dev settings
PORT=3000
```

---

## 📂 File Structure Directory

```files
/bots
  ├── user_bot.py      # QuickCVBot - FSM wizard engine & downloads
  ├── admin_bot.py     # QuickCVPanelBot - Admin controls & models
  └── credit_bot.py    # QuickCVCreditBot - Transaction notifications
/config
  ├── settings.py      # App configs & Render storage path mounts
  └── generator.py     # OpenCode AI, ReportLab PDF, and DOCX files compiler
/database
  └── db_manager.py    # SQLite connections pool & seeding
/generated_resumes/    # Compiled resumes storage
/logs/                 # Local system records
main.py                # Process initiator, long polling gatherer, telemetry server
requirements.txt       # Unified Python dependencies manifest
render.yaml            # Render Blueprint Deploy model
```

---

## 🔌 Running Locally

1. **Clone project and navigate to the root directory:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Execute the local background runner:**
   ```bash
   python main.py
   ```
This initiates all 3 long polling listeners, runs migrations, and hosts the visual diagnostics console locally on http://localhost:3000.

---

## 🚀 Deploying to Render.com

QuickCV is optimized for **Render Background Worker** deployments.

1. **Add Persistent Disk Storage:**
   In your Render.com dashboard, bind a **1 GB Persistent Disk** storage mounted at `/data`.
   This ensures your SQLite database file (`quickcv.db`) remains completely intact and intact across service upgrades or restarts.

2. **Deploy using render.yaml:**
   Simply link this GitHub repository directly to Render, and it will auto-provision the Background Worker dynamically, install all requirements, and boot up our multi-bot telemetry engine.

---

## 📚 Administrator Commands Catalog

Add your ID to `ADMIN_IDS`. Message `QuickCVPanelBot` to make use of:

- `/start` - Access commands catalogue.
- `/dashboard` - Overview user accounts, resumes built, today's metrics, and active selected model.
- `/users` - Interactive profiles manager. Search users by handle, grant/reduce user credits, set VIP unlimited tokens, or ban/unban profiles.
- `/models` - Configure and switch active model. (Saves selection immediately in SQLite. No code reboot required!).
- `/broadcast` - Dispatch alerts to all users. Supports formatting and images.
- `/credits <id> <amount>` - Direct credits adjustments.
- `/ban` / `/unban` - Block/unblock access.
- `/logs` - Inspect recent security logs.
