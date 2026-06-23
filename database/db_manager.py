import sqlite3
import datetime
import uuid
import json
from config.settings import DB_PATH, ADMIN_IDS, DEFAULT_MODEL_ID, SUPPORTED_MODELS

class DBManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except:
            pass
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TEXT,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    is_banned INTEGER DEFAULT 0
                )
            """)

            # 2. Admins Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    added_at TEXT
                )
            """)

            # 3. Credits Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credits (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 2,
                    last_claimed_reward TEXT,
                    unlimited INTEGER DEFAULT 0
                )
            """)

            # 4. Resumes Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT,
                    file_path_pdf TEXT,
                    file_path_docx TEXT,
                    model_used TEXT,
                    created_at TEXT,
                    content TEXT
                )
            """)

            # 5. Settings Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 6. Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    category TEXT,
                    message TEXT,
                    user_id INTEGER
                )
            """)

            # 7. Referrals Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referee_id INTEGER,
                    timestamp TEXT,
                    rewarded INTEGER DEFAULT 0
                )
            """)

            # 8. Banned Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS banned_users (
                    user_id INTEGER PRIMARY KEY,
                    reason TEXT,
                    banned_at TEXT
                )
            """)
            
            # Column-level self-healing migrations
            try:
                cursor.execute("ALTER TABLE credits ADD COLUMN unlimited INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            conn.commit()

        # Seed initial models and settings
        self.seed_defaults()

    def seed_defaults(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Seed default active model
            cursor.execute("SELECT 1 FROM settings WHERE key = ?", ("active_model_id",))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("active_model_id", DEFAULT_MODEL_ID))

            # Seed supported models list in settings table as JSON
            cursor.execute("SELECT 1 FROM settings WHERE key = ?", ("models_list",))
            if not cursor.fetchone():
                models_json = json.dumps(SUPPORTED_MODELS)
                cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("models_list", models_json))

            # Seed static admins from environment config
            now = datetime.datetime.now().isoformat()
            for admin_id in ADMIN_IDS:
                cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (admin_id, now))
                
            conn.commit()

    # --- LOGS HELPERS ---
    def add_log(self, level, category, message, user_id=None):
        timestamp = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO logs (timestamp, level, category, message, user_id) VALUES (?, ?, ?, ?, ?)",
                (timestamp, level, category, message, user_id)
            )

    def get_logs(self, limit=100):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # --- USER METHODS ---
    def get_or_create_user(self, user_id, username, first_name, last_name, referred_by=None):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            
            if user:
                return dict(user)
            
            # Generate unique referral code
            ref_code = str(uuid.uuid4())[:8].upper()
            
            # Insert User
            cursor.execute(
                "INSERT INTO users (id, username, first_name, last_name, joined_at, referral_code, referred_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, first_name, last_name, now, ref_code, referred_by)
            )
            
            # Insert Credit Profile (New user gets 2 free credits)
            cursor.execute(
                "INSERT OR IGNORE INTO credits (user_id, balance, unlimited) VALUES (?, 2, 0)",
                (user_id,)
            )
            
            self.add_log("INFO", "USER_JOINED", f"New user joined: {first_name} (@{username})", user_id)
            
            # Process referral if referee entered code
            if referred_by and referred_by != user_id:
                # Add Referral entry
                cursor.execute(
                    "INSERT INTO referrals (referrer_id, referee_id, timestamp, rewarded) VALUES (?, ?, ?, 1)",
                    (referred_by, user_id, now)
                )
                # Direct credit bonus +1 to referrer
                cursor.execute(
                    "UPDATE credits SET balance = balance + 1 WHERE user_id = ?",
                    (referred_by,)
                )
                self.add_log("INFO", "REFERRAL_USED", f"User {user_id} registered under {referred_by}. +1 credit to referrer.", referred_by)
                
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return dict(cursor.fetchone())

    def get_user_by_referral_code(self, code):
        if not code:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE referral_code = ?", (code.upper().strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- CREDIT SERVICES ---
    def get_credits(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance, last_claimed_reward, unlimited FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            else:
                # Initialize credits structure if missing
                cursor.execute("INSERT INTO credits (user_id, balance) VALUES (?, 2)", (user_id,))
                conn.commit()
                return {"balance": 2, "last_claimed_reward": None, "unlimited": 0}

    def claim_daily_reward(self, user_id):
        now = datetime.datetime.now()
        now_str = now.isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_claimed_reward, balance FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                cursor.execute("INSERT INTO credits (user_id, balance, last_claimed_reward) VALUES (?, 4, ?)", (user_id, now_str))
                conn.commit()
                self.add_log("INFO", "CREDIT_CLAIMED", "Claimed first daily reward (+2 credits)", user_id)
                return True, "Success! You received 2 Credits.", 24 * 3600
                
            last_claimed = row["last_claimed_reward"]
            if last_claimed:
                try:
                    last_dt = datetime.datetime.fromisoformat(last_claimed)
                    elapsed = now - last_dt
                    if elapsed < datetime.timedelta(hours=24):
                        time_left_sec = int((datetime.timedelta(hours=24) - elapsed).total_seconds())
                        return False, f"You can claim your next reward in {time_left_sec // 3600}h {(time_left_sec % 3600) // 60}m limit.", time_left_sec
                except ValueError:
                    pass # treat corrupted as eligible to claim
            
            # Eligible to claim
            cursor.execute(
                "UPDATE credits SET balance = balance + 2, last_claimed_reward = ? WHERE user_id = ?",
                (now_str, user_id)
            )
            conn.commit()
            self.add_log("INFO", "CREDIT_CLAIMED", "Daily reward claimed (+2 credits)", user_id)
            return True, "Daily Reward Claimed! +2 credits added to your balance.", 24 * 3600

    def consume_credit(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance, unlimited FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                # auto provision
                cursor.execute("INSERT INTO credits (user_id, balance) VALUES (?, 2)", (user_id,))
                conn.commit()
                return True
                
            if row["unlimited"] == 1:
                return True # unlimited credits
                
            if row["balance"] >= 1:
                cursor.execute("UPDATE credits SET balance = balance - 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            return False

    def modify_credits(self, user_id, amount, set_unlimited=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if set_unlimited is not None:
                cursor.execute("UPDATE credits SET unlimited = ? WHERE user_id = ?", (1 if set_unlimited else 0, user_id))
            else:
                cursor.execute("UPDATE credits SET balance = MAX(0, balance + ?) WHERE user_id = ?", (amount, user_id))
            conn.commit()
            self.add_log("ADMIN_ACTION", "CREDIT_MODIFIED", f"Credits updated for user {user_id}. Amount={amount if set_unlimited is None else 'UNLIMITED'}", user_id)

    # --- BANNING CONTROL ---
    def ban_user(self, user_id, reason):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
            cursor.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_at) VALUES (?, ?, ?)", (user_id, reason, now))
            conn.commit()
            self.add_log("ADMIN_ACTION", "USER_BANNED", f"Banned user {user_id} for: {reason}", user_id)

    def unban_user(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
            conn.commit()
            self.add_log("ADMIN_ACTION", "USER_UNBANNED", f"Unbanned user {user_id}", user_id)

    def is_banned(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row["is_banned"] == 1:
                return True
            return False

    # --- ADMIN PRIVILEGES ---
    def is_admin(self, user_id):
        if user_id in ADMIN_IDS:
            return True
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None

    def add_admin(self, user_id):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, now))
            conn.commit()
            self.add_log("ADMIN_ACTION", "ADMIN_ADDED", f"Granted admin role to {user_id}", user_id)

    def remove_admin(self, user_id):
        if user_id in ADMIN_IDS:
            return False # Cannot remove environment level admins
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()
            self.add_log("ADMIN_ACTION", "ADMIN_REMOVED", f"Revoked admin role from {user_id}", user_id)
            return True

    # --- RESUME REGISTRY ---
    def save_resume(self, user_id, title, pdf_path, docx_path, model_used, content):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO resumes (user_id, title, file_path_pdf, file_path_docx, model_used, created_at, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, title, pdf_path, docx_path, model_used, now, content)
            )
            conn.commit()
            self.add_log("INFO", "RESUME_GENERATED", f"Generated resume: {title} via model: {model_used}", user_id)
            return cursor.lastrowid

    def get_user_resumes(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM resumes WHERE user_id = ? ORDER BY id DESC", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    # --- CONFIGURATION SETTINGS ---
    def get_setting(self, key, default=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key, value):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_models(self):
        models_json = self.get_setting("models_list")
        if models_json:
            return json.loads(models_json)
        return SUPPORTED_MODELS

    def save_models(self, models_list):
        self.set_setting("models_list", json.dumps(models_list))

    def get_active_model(self):
        active_id = self.get_setting("active_model_id", DEFAULT_MODEL_ID)
        models = self.get_models()
        for m in models:
            if m["model_id"] == active_id and m["enabled"]:
                return m
        # Fallback to first enabled model or default
        for m in models:
            if m["enabled"]:
                return m
        return {"display_name": "DeepSeek V4 Flash Free", "model_id": DEFAULT_MODEL_ID, "enabled": True}

    # --- STATS REPORTING ---
    def get_dashboard_stats(self):
        now_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        stats = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Total Users
            cursor.execute("SELECT COUNT(*) FROM users")
            stats["total_users"] = cursor.fetchone()[0]
            
            # Active Users (have generated a resume or claimed daily credits)
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM credits")
            stats["active_users"] = cursor.fetchone()[0]
            
            # Today's Users
            cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{now_date_str}%",))
            stats["todays_users"] = cursor.fetchone()[0]
            
            # Total Resumes
            cursor.execute("SELECT COUNT(*) FROM resumes")
            stats["total_resumes"] = cursor.fetchone()[0]
            
            # Today's Resumes
            cursor.execute("SELECT COUNT(*) FROM resumes WHERE created_at LIKE ?", (f"{now_date_str}%",))
            stats["todays_resumes"] = cursor.fetchone()[0]
            
            # Credits Used vs Remaining
            # Total starting credits per user is 2. plus whatever refer / daily.
            # We can aggregate total balance
            cursor.execute("SELECT SUM(balance) FROM credits")
            stats["credits_remaining"] = cursor.fetchone()[0] or 0
            
            # We can approximate used credits from log history of RESUME_GENERATED
            cursor.execute("SELECT COUNT(*) FROM logs WHERE category = 'RESUME_GENERATED'")
            stats["credits_used"] = cursor.fetchone()[0] or 0
            
        return stats

    def get_all_users_for_admin(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.*, c.balance, c.unlimited, b.reason as ban_reason
                FROM users u
                LEFT JOIN credits c ON u.id = c.user_id
                LEFT JOIN banned_users b ON u.id = b.user_id
                ORDER BY u.joined_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def search_user_by_query(self, query):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if query.isdigit():
                cursor.execute("""
                    SELECT u.*, c.balance, c.unlimited, b.reason as ban_reason
                    FROM users u
                    LEFT JOIN credits c ON u.id = c.user_id
                    LEFT JOIN banned_users b ON u.id = b.user_id
                    WHERE u.id = ?
                """, (int(query),))
            else:
                q = f"%{query}%"
                cursor.execute("""
                    SELECT u.*, c.balance, c.unlimited, b.reason as ban_reason
                    FROM users u
                    LEFT JOIN credits c ON u.id = c.user_id
                    LEFT JOIN banned_users b ON u.id = b.user_id
                    WHERE u.username LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ?
                """, (q, q, q))
            return [dict(row) for row in cursor.fetchall()]

    def delete_user_all_data(self, user_id):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM credits WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM resumes WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM referrals WHERE referrer_id = ? OR referee_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()
            self.add_log("ADMIN_ACTION", "USER_DELETED_ALL", f"Deleted all data for user ID {user_id}", user_id)
