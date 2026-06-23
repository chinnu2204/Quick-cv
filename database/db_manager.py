import sqlite3
import datetime
import uuid
import json
import time
import sys
from config.settings import DB_PATH, ADMIN_IDS, DEFAULT_MODEL_ID, SUPPORTED_MODELS

class DBManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        except Exception as e:
            print(f"Warning: Failed to set PRAGMAs: {e}", file=sys.stderr)
        return conn

    def _run_with_retry(self, action_func, *args, **kwargs):
        """
        Runs action_func (which takes a connection as its first argument) under retry logic
        specifically catching sqlite3.OperationalError: database is locked.
        """
        delay_times = [0.2, 0.5, 1.0, 2.0, 5.0]
        max_retries = len(delay_times)
        
        for attempt in range(max_retries + 1):
            conn = self._get_connection()
            try:
                with conn:
                    result = action_func(conn, *args, **kwargs)
                return result
            except sqlite3.OperationalError as e:
                err_msg = str(e).lower()
                if "locked" in err_msg or "busy" in err_msg:
                    if attempt < max_retries:
                        sleep_time = delay_times[attempt]
                        time.sleep(sleep_time)
                        continue
                raise e
            finally:
                conn.close()

    def _init_db(self):
        def _init(conn):
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
            
        self._run_with_retry(_init)

        # Seed initial models and settings
        self.seed_defaults()

    def seed_defaults(self):
        def _seed(conn):
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
                
        self._run_with_retry(_seed)

    # --- LOGS HELPERS ---
    def add_log(self, level, category, message, user_id=None, conn=None):
        timestamp = datetime.datetime.now().isoformat()
        try:
            if conn is not None:
                conn.execute(
                    "INSERT INTO logs (timestamp, level, category, message, user_id) VALUES (?, ?, ?, ?, ?)",
                    (timestamp, level, category, message, user_id)
                )
            else:
                def _write(c):
                    c.execute(
                        "INSERT INTO logs (timestamp, level, category, message, user_id) VALUES (?, ?, ?, ?, ?)",
                        (timestamp, level, category, message, user_id)
                    )
                self._run_with_retry(_write)
        except Exception as e:
            # Fix add_log() specifically because it is crashing user registration.
            # If log insertion fails: Do not crash bot. Print warning and continue.
            print(f"Warning: Failed to insert log ({level}, {category}, {message}): {e}", file=sys.stderr)

    def get_logs(self, limit=100):
        def _get(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        return self._run_with_retry(_get)

    # --- USER METHODS ---
    def get_or_create_user(self, user_id, username, first_name, last_name, referred_by=None):
        now = datetime.datetime.now().isoformat()
        
        def _get_or_create(conn):
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
            
            # Ensure logging failure doesn't crash user creations
            try:
                self.add_log("INFO", "USER_JOINED", f"New user joined: {first_name} (@{username})", user_id, conn=conn)
            except Exception:
                pass
            
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
                try:
                    self.add_log("INFO", "REFERRAL_USED", f"User {user_id} registered under {referred_by}. +1 credit to referrer.", referred_by, conn=conn)
                except Exception:
                    pass
                
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return dict(cursor.fetchone())

        return self._run_with_retry(_get_or_create)

    def get_user_by_referral_code(self, code):
        if not code:
            return None
        def _get(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE referral_code = ?", (code.upper().strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None
        return self._run_with_retry(_get)

    # --- CREDIT SERVICES ---
    def get_credits(self, user_id):
        def _get_helper(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT balance, last_claimed_reward, unlimited FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            else:
                # Initialize credits structure if missing
                cursor.execute("INSERT INTO credits (user_id, balance) VALUES (?, 2)", (user_id,))
                return {"balance": 2, "last_claimed_reward": None, "unlimited": 0}
        return self._run_with_retry(_get_helper)

    def claim_daily_reward(self, user_id):
        now = datetime.datetime.now()
        now_str = now.isoformat()
        
        def _claim(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT last_claimed_reward, balance FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if not row:
                cursor.execute("INSERT INTO credits (user_id, balance, last_claimed_reward) VALUES (?, 4, ?)", (user_id, now_str))
                try:
                    self.add_log("INFO", "CREDIT_CLAIMED", "Claimed first daily reward (+2 credits)", user_id, conn=conn)
                except Exception:
                    pass
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
            try:
                self.add_log("INFO", "CREDIT_CLAIMED", "Daily reward claimed (+2 credits)", user_id, conn=conn)
            except Exception:
                pass
            return True, "Daily Reward Claimed! +2 credits added to your balance.", 24 * 3600

        return self._run_with_retry(_claim)

    def consume_credit(self, user_id):
        def _consume(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT balance, unlimited FROM credits WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                # auto provision
                cursor.execute("INSERT INTO credits (user_id, balance) VALUES (?, 2)", (user_id,))
                return True
                
            if row["unlimited"] == 1:
                return True # unlimited credits
                
            if row["balance"] >= 1:
                cursor.execute("UPDATE credits SET balance = balance - 1 WHERE user_id = ?", (user_id,))
                return True
            return False

        return self._run_with_retry(_consume)

    def modify_credits(self, user_id, amount, set_unlimited=None):
        def _modify(conn):
            cursor = conn.cursor()
            if set_unlimited is not None:
                cursor.execute("UPDATE credits SET unlimited = ? WHERE user_id = ?", (1 if set_unlimited else 0, user_id))
            else:
                cursor.execute("UPDATE credits SET balance = MAX(0, balance + ?) WHERE user_id = ?", (amount, user_id))
            try:
                self.add_log("ADMIN_ACTION", "CREDIT_MODIFIED", f"Credits updated for user {user_id}. Amount={amount if set_unlimited is None else 'UNLIMITED'}", user_id, conn=conn)
            except Exception:
                pass
                
        self._run_with_retry(_modify)

    # --- BANNING CONTROL ---
    def ban_user(self, user_id, reason):
        now = datetime.datetime.now().isoformat()
        def _ban(conn):
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
            cursor.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_at) VALUES (?, ?, ?)", (user_id, reason, now))
            try:
                self.add_log("ADMIN_ACTION", "USER_BANNED", f"Banned user {user_id} for: {reason}", user_id, conn=conn)
            except Exception:
                pass
                
        self._run_with_retry(_ban)

    def unban_user(self, user_id):
        def _unban(conn):
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
            try:
                self.add_log("ADMIN_ACTION", "USER_UNBANNED", f"Unbanned user {user_id}", user_id, conn=conn)
            except Exception:
                pass
                
        self._run_with_retry(_unban)

    def is_banned(self, user_id):
        def _is_b(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row["is_banned"] == 1:
                return True
            return False
        return self._run_with_retry(_is_b)

    # --- ADMIN PRIVILEGES ---
    def is_admin(self, user_id):
        if user_id in ADMIN_IDS:
            return True
        def _is_a(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None
        return self._run_with_retry(_is_a)

    def add_admin(self, user_id):
        now = datetime.datetime.now().isoformat()
        def _add(conn):
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, now))
            try:
                self.add_log("ADMIN_ACTION", "ADMIN_ADDED", f"Granted admin role to {user_id}", user_id, conn=conn)
            except Exception:
                pass
                
        self._run_with_retry(_add)

    def remove_admin(self, user_id):
        if user_id in ADMIN_IDS:
            return False # Cannot remove environment level admins
        def _remove(conn):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            try:
                self.add_log("ADMIN_ACTION", "ADMIN_REMOVED", f"Revoked admin role from {user_id}", user_id, conn=conn)
            except Exception:
                pass
            return True
            
        return self._run_with_retry(_remove)

    # --- RESUME REGISTRY ---
    def save_resume(self, user_id, title, pdf_path, docx_path, model_used, content):
        now = datetime.datetime.now().isoformat()
        def _save(conn):
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO resumes (user_id, title, file_path_pdf, file_path_docx, model_used, created_at, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, title, pdf_path, docx_path, model_used, now, content)
            )
            last_id = cursor.lastrowid
            try:
                self.add_log("INFO", "RESUME_GENERATED", f"Generated resume: {title} via model: {model_used}", user_id, conn=conn)
            except Exception:
                pass
            return last_id
            
        return self._run_with_retry(_save)

    def get_user_resumes(self, user_id):
        def _get(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM resumes WHERE user_id = ? ORDER BY id DESC", (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        return self._run_with_retry(_get)

    # --- CONFIGURATION SETTINGS ---
    def get_setting(self, key, default=None):
        def _get(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
        return self._run_with_retry(_get)

    def set_setting(self, key, value):
        def _set(conn):
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self._run_with_retry(_set)

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
        
        def _get_stats(conn):
            cursor = conn.cursor()
            stats = {}
            
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
            cursor.execute("SELECT SUM(balance) FROM credits")
            stats["credits_remaining"] = cursor.fetchone()[0] or 0
            
            # We can approximate used credits from log history of RESUME_GENERATED
            cursor.execute("SELECT COUNT(*) FROM logs WHERE category = 'RESUME_GENERATED'")
            stats["credits_used"] = cursor.fetchone()[0] or 0
            
            return stats

        return self._run_with_retry(_get_stats)

    def get_all_users_for_admin(self):
        def _get(conn):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.*, c.balance, c.unlimited, b.reason as ban_reason
                FROM users u
                LEFT JOIN credits c ON u.id = c.user_id
                LEFT JOIN banned_users b ON u.id = b.user_id
                ORDER BY u.joined_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
        return self._run_with_retry(_get)

    def search_user_by_query(self, query):
        def _search(conn):
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
        return self._run_with_retry(_search)

    def delete_user_all_data(self, user_id):
        def _delete(conn):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM credits WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM resumes WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM referrals WHERE referrer_id = ? OR referee_id = ?", (user_id, user_id))
            cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            try:
                self.add_log("ADMIN_ACTION", "USER_DELETED_ALL", f"Deleted all data for user ID {user_id}", user_id, conn=conn)
            except Exception:
                pass
                
        self._run_with_retry(_delete)
