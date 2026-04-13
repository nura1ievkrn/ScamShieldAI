from flask import Flask, render_template, request, session, redirect, jsonify, url_for
import os
import json
import re
import requests
import base64
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    t = get_t()
    lang = get_lang()
    return render_template("login.html", t=t, lang=lang,
                           error="Сессия устарела. Повторите попытку."), 400

# ─── DATABASE ─────────────────────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

load_dotenv()

# ─── OPENROUTER CONFIG ────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
# Fallback chain — if one hits 429, tries the next
FREE_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-3n-e2b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-0.6b:free",
    "microsoft/phi-3-mini-128k-instruct:free",
]
# Vision models — openrouter/free auto-selects vision-capable model
VISION_MODELS = [
    "openrouter/free",                              # auto-routes to best free vision model
    "google/gemma-3n-e4b-it:free",                  # Gemma 3n multimodal (vision+text)
    "google/gemma-3n-e2b-it:free",                  # Gemma 3n smaller
    "stepfun/step-3.5-flash:free",                  # StepFun multimodal
    "minimax/minimax-m2.5:free",                    # MiniMax multimodal
]


def call_openrouter(messages, max_tokens=900, system_prompt=None):
    """
    Universal OpenRouter API call with automatic fallback.
    If a model returns 429 (rate limit) — tries the next one in FREE_MODELS list.
    All free models don't support 'system' role — merged into user message.
    """
    all_messages = list(messages)
    if system_prompt and all_messages:
        first = all_messages[0]
        all_messages[0] = {
            "role": "user",
            "content": system_prompt + "\n\n" + (first.get("content") or ""),
        }
    elif system_prompt:
        all_messages = [{"role": "user", "content": system_prompt}]

    last_error = None
    for model in FREE_MODELS:
        try:
            response = requests.post(
                url=OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://scamshield.kz",
                    "X-Title": "ScamShield AI",
                },
                data=json.dumps({
                    "model":       model,
                    "max_tokens":  max_tokens,
                    "temperature": 0.3,
                    "top_p":       0.9,
                    "messages":    all_messages,
                }),
                timeout=30,
            )
            # 429 = rate limit → try next model
            if response.status_code == 429:
                last_error = f"429 on {model}"
                continue
            response.raise_for_status()
            data    = response.json()
            content = data["choices"][0]["message"]["content"]
            return content or "❌ Empty response from AI"
        except requests.exceptions.Timeout:
            last_error = f"Timeout on {model}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    return f"❌ Барлық модельдер қол жетімді емес. Кейінірек қайталаңыз. ({last_error})"


# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    id                = db.Column(db.Integer, primary_key=True)
    username          = db.Column(db.String(100), unique=True)
    email             = db.Column(db.String(200))
    password_hash     = db.Column(db.String(200))
    is_admin          = db.Column(db.Boolean, default=False)
    plan              = db.Column(db.String(20), default='free')   # free / pro / business
    requests_today    = db.Column(db.Integer, default=0)
    last_request_date = db.Column(db.String(20), default='')
    created_at        = db.Column(db.String(30), default='')
    # Settings
    theme             = db.Column(db.String(10), default='dark')
    notifications     = db.Column(db.Boolean, default=True)
    language          = db.Column(db.String(5),  default='kz')
    deep_analysis     = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_daily_limit(self):
        return {'free': 10, 'pro': 100, 'business': 999999}.get(self.plan, 10)

    def can_request(self):
        today = str(date.today())
        if self.last_request_date != today:
            self.requests_today    = 0
            self.last_request_date = today
            db.session.commit()
        return self.requests_today < self.get_daily_limit()

    def increment_requests(self):
        today = str(date.today())
        if self.last_request_date != today:
            self.requests_today    = 0
            self.last_request_date = today
        self.requests_today += 1
        db.session.commit()


class DailyStats(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    date          = db.Column(db.String(20), unique=True)
    total_checks  = db.Column(db.Integer, nullable=False, default=0)
    scam_detected = db.Column(db.Integer, nullable=False, default=0)
    safe_detected = db.Column(db.Integer, nullable=False, default=0)
    phone_checks  = db.Column(db.Integer, nullable=False, default=0)
    link_checks   = db.Column(db.Integer, nullable=False, default=0)
    text_checks   = db.Column(db.Integer, nullable=False, default=0)


def update_stats(score, check_type='text'):
    today = str(date.today())
    stat  = DailyStats.query.filter_by(date=today).first()
    if not stat:
        stat = DailyStats(date=today, total_checks=0, scam_detected=0,
                          safe_detected=0, phone_checks=0, link_checks=0, text_checks=0)
        db.session.add(stat)
        db.session.flush()
    stat.total_checks  = (stat.total_checks  or 0) + 1
    if score >= 60:
        stat.scam_detected = (stat.scam_detected or 0) + 1
    else:
        stat.safe_detected = (stat.safe_detected or 0) + 1
    if check_type == 'phone':
        stat.phone_checks = (stat.phone_checks or 0) + 1
    elif check_type == 'link':
        stat.link_checks  = (stat.link_checks  or 0) + 1
    else:
        stat.text_checks  = (stat.text_checks  or 0) + 1
    db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── TRANSLATIONS ─────────────────────────────────────────────────────────────

TRANSLATIONS = {
    "kz": {
        "title": "ScamShield AI", "subtitle": "Алаяқтықты анықтаңыз",
        "new_chat": "Жаңа чат", "statistics": "Статистика",
        "phone_check": "Нөмірді тексеру", "link_check": "Сілтемені тексеру",
        "history": "Тарих", "plans": "Жоспарлар", "settings": "Параметрлер",
        "placeholder": "Хабарлама, нөмір немесе сілтемені енгізіңіз...",
        "login": "Кіру", "register": "Тіркелу", "logout": "Шығу",
        "profile": "Профиль", "username": "Пайдаланушы аты",
        "password": "Құпия сөз", "confirm_password": "Құпия сөзді растаңыз",
        "email": "Email", "today_checks": "Бүгін тексерілді",
        "scam_found": "Алаяқтық анықталды", "safe_found": "Қауіпсіз",
        "free_plan": "Тегін жоспар", "pro_plan": "Pro жоспары",
        "business_plan": "Бизнес жоспары", "requests_left": "сұраныс қалды",
        "dark_mode": "Түнгі режим", "light_mode": "Күндізгі режим",
        "notifications": "Хабарландырулар", "deep_analysis": "Терең анализ",
        "save_settings": "Сақтау", "risk_low": "Төмен қауіп",
        "risk_medium": "Орташа қауіп", "risk_high": "Жоғары қауіп",
        "analyzing": "Анализдеу...",
        "limit_reached": "Күнделікті лимит таусылды. Pro жоспарына өтіңіз.",
        "passwords_no_match": "Құпия сөздер сәйкес емес",
        "user_exists": "Бұл пайдаланушы аты бос емес",
        "login_error": "Қате логин немесе құпия сөз",
        "welcome": "Қош келдіңіз", "send": "Жіберу",
        "chat_title": "Жаңа чат", "no_history": "Тарих жоқ",
        "monthly": "айына", "per_req": "сұраныс/күн", "unlimited": "Шексіз",
    },
    "ru": {
        "title": "ScamShield AI", "subtitle": "Определите мошенничество",
        "new_chat": "Новый чат", "statistics": "Статистика",
        "phone_check": "Проверка номера", "link_check": "Проверка ссылки",
        "history": "История", "plans": "Планы", "settings": "Параметры",
        "placeholder": "Введите сообщение, номер или ссылку...",
        "login": "Войти", "register": "Регистрация", "logout": "Выйти",
        "profile": "Профиль", "username": "Имя пользователя",
        "password": "Пароль", "confirm_password": "Подтвердите пароль",
        "email": "Email", "today_checks": "Проверено сегодня",
        "scam_found": "Обнаружено мошенничеств", "safe_found": "Безопасных",
        "free_plan": "Бесплатный план", "pro_plan": "Pro план",
        "business_plan": "Бизнес план", "requests_left": "запросов осталось",
        "dark_mode": "Тёмный режим", "light_mode": "Светлый режим",
        "notifications": "Уведомления", "deep_analysis": "Глубокий анализ",
        "save_settings": "Сохранить", "risk_low": "Низкий риск",
        "risk_medium": "Средний риск", "risk_high": "Высокий риск",
        "analyzing": "Анализирую...",
        "limit_reached": "Дневной лимит исчерпан. Перейдите на Pro план.",
        "passwords_no_match": "Пароли не совпадают",
        "user_exists": "Это имя пользователя занято",
        "login_error": "Неверный логин или пароль",
        "welcome": "Добро пожаловать", "send": "Отправить",
        "chat_title": "Новый чат", "no_history": "История пуста",
        "monthly": "в месяц", "per_req": "запросов/день", "unlimited": "Безлимит",
    },
    "en": {
        "title": "ScamShield AI", "subtitle": "Detect scams instantly",
        "new_chat": "New chat", "statistics": "Statistics",
        "phone_check": "Phone check", "link_check": "Link check",
        "history": "History", "plans": "Plans", "settings": "Settings",
        "placeholder": "Enter message, phone number or link...",
        "login": "Login", "register": "Register", "logout": "Logout",
        "profile": "Profile", "username": "Username",
        "password": "Password", "confirm_password": "Confirm password",
        "email": "Email", "today_checks": "Checked today",
        "scam_found": "Scams detected", "safe_found": "Safe",
        "free_plan": "Free plan", "pro_plan": "Pro plan",
        "business_plan": "Business plan", "requests_left": "requests left",
        "dark_mode": "Dark mode", "light_mode": "Light mode",
        "notifications": "Notifications", "deep_analysis": "Deep analysis",
        "save_settings": "Save", "risk_low": "Low risk",
        "risk_medium": "Medium risk", "risk_high": "High risk",
        "analyzing": "Analyzing...",
        "limit_reached": "Daily limit reached. Upgrade to Pro.",
        "passwords_no_match": "Passwords don't match",
        "user_exists": "Username already taken",
        "login_error": "Invalid username or password",
        "welcome": "Welcome", "send": "Send",
        "chat_title": "New chat", "no_history": "No history",
        "monthly": "per month", "per_req": "requests/day", "unlimited": "Unlimited",
    },
}

# Keep T as alias for backward compat inside routes that use T[lang]
T = TRANSLATIONS

# ─── SCAM TYPE LABELS ─────────────────────────────────────────────────────────

SCAM_TYPES = {
    "kz": {
        "PHISHING":           "Фишинг (жалған сайт/форма)",
        "FINANCIAL_PYRAMID":  "Қаржылық пирамида",
        "ROMANCE_SCAM":       "Романтикалық алдау",
        "LOTTERY_SCAM":       "Жалған ұтыс/сыйлық",
        "TECH_SUPPORT":       "Жалған техникалық қолдау",
        "ADVANCE_FEE":        "Алдын ала төлем алаяқтығы",
        "IMPERSONATION":      "Банк/полиция/мемлекет атынан алдау",
        "MARKETPLACE_FRAUD":  "Онлайн сауда алаяқтығы",
        "CRYPTO_SCAM":        "Крипто алаяқтығы",
        "JOB_SCAM":           "Жалған жұмыс ұсынысы",
        "UNKNOWN":            "Белгісіз",
    },
    "ru": {
        "PHISHING":           "Фишинг",
        "FINANCIAL_PYRAMID":  "Финансовая пирамида",
        "ROMANCE_SCAM":       "Романтическая афера",
        "LOTTERY_SCAM":       "Фейковый выигрыш/приз",
        "TECH_SUPPORT":       "Фейковая техподдержка",
        "ADVANCE_FEE":        "Мошенничество с предоплатой",
        "IMPERSONATION":      "Выдача себя за банк/полицию",
        "MARKETPLACE_FRAUD":  "Торговое мошенничество",
        "CRYPTO_SCAM":        "Крипто-мошенничество",
        "JOB_SCAM":           "Фейковая вакансия",
        "UNKNOWN":            "Неизвестно",
    },
    "en": {
        "PHISHING":           "Phishing",
        "FINANCIAL_PYRAMID":  "Financial Pyramid",
        "ROMANCE_SCAM":       "Romance Scam",
        "LOTTERY_SCAM":       "Lottery/Prize Scam",
        "TECH_SUPPORT":       "Fake Tech Support",
        "ADVANCE_FEE":        "Advance Fee Fraud",
        "IMPERSONATION":      "Bank/Gov Impersonation",
        "MARKETPLACE_FRAUD":  "Marketplace Fraud",
        "CRYPTO_SCAM":        "Crypto Scam",
        "JOB_SCAM":           "Job Scam",
        "UNKNOWN":            "Unknown",
    },
}

# ─── GEMMA SYSTEM PROMPT (short & strict — works best for small models) ───────

SYSTEM_PROMPT = """ScamShield AI — Kazakhstan fraud detector. Reply ONLY in this format, nothing else:

SCAM_TYPE: [PHISHING|FINANCIAL_PYRAMID|ROMANCE_SCAM|LOTTERY_SCAM|TECH_SUPPORT|ADVANCE_FEE|IMPERSONATION|MARKETPLACE_FRAUD|CRYPTO_SCAM|JOB_SCAM|UNKNOWN]
SCORE: [0-100, specific number e.g. 73 not 70]
TRIGGERS: [URGENCY,FEAR,GREED,AUTHORITY,SCARCITY,SECRECY or NONE]

KAZAKH:
Қауіп деңгейі: [Төмен/Орташа/Жоғары]
Алаяқтық түрі: [Kazakh type]
Себептер:
- [reason 1]
- [reason 2]
Не істеу керек:
- [action 1]
- [action 2]

RUSSIAN:
Уровень риска: [Низкий/Средний/Высокий]
Тип: [Russian type]
Причины:
- [reason 1]
- [reason 2]
Что делать:
- [action 1]
- [action 2]

ENGLISH:
Risk: [Low/Medium/High]
Type: [type]
Reasons:
- [reason 1]
Actions:
- [action 1]

Score: +20 OTP/card request, +15 money transfer, +12 fake brand, +10 urgency/fear, -10 official domain"""

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_lang():
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")

def get_t():
    return TRANSLATIONS[get_lang()]

def extract_score(text):
    if not text:
        return 0
    m = re.search(r'^SCORE:\s*(\d+)', text, re.MULTILINE)
    if m:
        return min(int(m.group(1)), 100)
    m = re.search(r'SCORE:\s*(\d+)', text, re.IGNORECASE)
    if m:
        return min(int(m.group(1)), 100)
    return 0

def extract_scam_type(text, lang="kz"):
    if not text:
        return "UNKNOWN", "Белгісіз"
    m    = re.search(r'^SCAM_TYPE:\s*(\w+)', text, re.MULTILINE | re.IGNORECASE)
    code = m.group(1).upper() if m else "UNKNOWN"
    label = SCAM_TYPES.get(lang, SCAM_TYPES["kz"]).get(code, code)
    return code, label

def extract_triggers(text):
    if not text:
        return []
    m = re.search(r'^TRIGGERS:\s*([^\n]+)', text, re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw.upper() in ["NONE", "ЖОҚ", "НЕТ", "-"]:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]

def extract_domain_trust(text):
    if not text:
        return None
    m = re.search(r'^DOMAIN_TRUST:\s*(\w+)', text, re.MULTILINE)
    return m.group(1).upper() if m else None

def extract_language_block(text, lang):
    """
    Output order in prompt: KAZAKH → RUSSIAN → ENGLISH
    Extract the right block and strip metadata lines.
    """
    if not text:
        return "❌ Жауап жоқ / Нет ответа"

    markers = {"kz": ("KAZAKH:", "RUSSIAN:"),
               "ru": ("RUSSIAN:", "ENGLISH:"),
               "en": ("ENGLISH:", None)}

    start_tag, end_tag = markers.get(lang, ("KAZAKH:", "RUSSIAN:"))
    start = text.find(start_tag)

    if start == -1:
        # Fallback: clean and return full text
        cleaned = re.sub(
            r'(SCAM_TYPE|SCORE|TRIGGERS|DOMAIN_TRUST):.*\n?', '', text
        )
        return cleaned.strip().replace("\n", "<br>")

    end = text.find(end_tag, start + 1) if end_tag else len(text)
    if end == -1:
        end = len(text)

    block = text[start:end].strip()
    # Remove metadata noise
    block = re.sub(r'SCORE:\s*\d+\n?', '', block)
    block = re.sub(r'SCAM_TYPE:\s*\S+\n?', '', block)
    block = re.sub(r'TRIGGERS:\s*[^\n]+\n?', '', block)
    block = re.sub(r'DOMAIN_TRUST:\s*\S+\n?', '', block)
    return block.strip().replace("\n", "<br>")


# ─── AI ANALYSIS FUNCTIONS ────────────────────────────────────────────────────

def analyze_text_ai(text, lang, deep=False):
    """Analyze message/text for scam — Gemma optimized."""
    extra = " Give 3-4 bullet points per section." if deep else " Give 2-3 bullet points per section."
    user_msg = (
        f"Analyze this text for scam signs.{extra}\n\n"
        f"Real Kazakhstan scam patterns to compare:\n"
        f"1. 'Ваш счёт взломан, переведите на защищённый счёт' → IMPERSONATION\n"
        f"2. 'Работа на дому 500$/день, предоплата за обучение' → JOB_SCAM\n"
        f"3. 'Ваш Kaspi заблокирован, назовите код из SMS' → PHISHING\n"
        f"4. 'Вы выиграли iPhone, оплатите доставку' → LOTTERY_SCAM\n"
        f"5. 'Инвестируй 50000₸ → получи 200000₸ за 3 дня' → FINANCIAL_PYRAMID\n\n"
        f"Text:\n\"\"\"{text}\"\"\""
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=800,
        system_prompt=SYSTEM_PROMPT,
    )


def analyze_phone_ai(phone, lang):
    """Analyze phone number for scam risk — Gemma optimized."""
    user_msg = (
        f"Analyze this Kazakhstan phone number for scam risk: {phone}\n\n"
        f"Risk patterns:\n"
        f"- +7700/708/747 = prepaid SIM often used by scammers\n"
        f"- Real bank lines: Kaspi=7272, Halyk=7077, BCC=7010\n"
        f"- Foreign numbers (+44,+1,+380) spoofed as local = HIGH risk\n"
        f"- VoIP / unusual patterns = suspicious\n\n"
        f"In KAZAKH block: say if user should call back or not.\n"
        f"In RUSSIAN block: same + what to do if already gave data.\n"
        f"Emergency contacts if scam: 102, cybercrime.kz"
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=700,
        system_prompt=SYSTEM_PROMPT,
    )


def analyze_link_ai(link, lang):
    """Analyze URL for phishing — Gemma optimized."""
    user_msg = (
        f"Analyze this URL for phishing targeting Kazakhstan users: {link}\n\n"
        f"Trusted official domains: kaspi.kz, halykbank.kz, egov.kz, enpf.kz, gov.kz\n"
        f"Known fake domains: kaspi-kz.com, halyk-bank.net, egov-kz.org, kaspi-pay.xyz\n"
        f"High-risk TLDs: .xyz .top .tk .ml .click .cf\n"
        f"Always risky: IP addresses, bit.ly/tinyurl shorteners\n\n"
        f"Check: Is domain real or typosquatted? Which brand is faked?\n"
        f"In KAZAKH block: visit or not + what to do if already clicked.\n"
        f"In RUSSIAN block: same detail + report to cybercrime.kz or cert.kz\n"
        f"Add DOMAIN_TRUST: [HIGH_TRUST/MEDIUM_TRUST/LOW_TRUST/NO_TRUST/FAKE_TRUST] after TRIGGERS line."
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=700,
        system_prompt=SYSTEM_PROMPT,
    )


def analyze_image_ai(file):
    """
    Image analysis — uses Gemini (vision capable).
    Gemma does NOT support vision.
    """
    image  = Image.open(file)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = (
        SYSTEM_PROMPT
        + "\n\nAnalyze this image for scam/fraud in Kazakhstan context.\n"
        "Look for: fake Kaspi/Halyk screenshots, fake prizes, fake job offers, "
        "suspicious QR codes, phishing pages, fake receipts, fake bank notifications."
    )

    messages = [{
        "role": "user",
        "content": [
            {"type": "text",      "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ],
    }]

    last_error = None
    for vision_model in VISION_MODELS:
        try:
            response = requests.post(
                url=OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://scamshield.kz",
                    "X-Title": "ScamShield AI",
                },
                data=json.dumps({
                    "model":      vision_model,
                    "max_tokens": 1000,
                    "messages":   messages,
                }),
                timeout=35,
            )
            if response.status_code in (404, 429):
                last_error = f"{response.status_code} on {vision_model}"
                continue
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            last_error = f"Timeout on {vision_model}"
            continue
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Суретті талдау мүмкін болмады. ({last_error})"


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/set_language/<lang>")
def set_language(lang):
    if lang in ['kz', 'ru', 'en']:
        session["lang"] = lang
        if current_user.is_authenticated:
            current_user.language = lang
            db.session.commit()
    return redirect(request.referrer or "/")


@app.route("/register", methods=["GET", "POST"])
def register():
    t = get_t()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        email    = request.form.get("email", "")
        if password != confirm:
            error = t["passwords_no_match"]
        elif User.query.filter_by(username=username).first():
            error = t["user_exists"]
        else:
            user = User(username=username, email=email, created_at=str(datetime.now()))
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect("/")
    return render_template("register.html", t=t, lang=get_lang(), error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    t = get_t()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect("/")
        error = t["login_error"]
    return render_template("login.html", t=t, lang=get_lang(), error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route("/profile")
@login_required
def profile():
    t = get_t()
    return render_template("profile.html", t=t, lang=get_lang(), user=current_user)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    t = get_t()
    if request.method == "POST":
        current_user.theme         = request.form.get("theme", "dark")
        current_user.notifications = "notifications" in request.form
        current_user.deep_analysis = "deep_analysis" in request.form
        db.session.commit()
        return redirect("/settings")
    return render_template("settings.html", t=t, lang=get_lang(), user=current_user)


@app.route("/statistics")
def statistics():
    t     = get_t()
    stats = DailyStats.query.order_by(DailyStats.date.desc()).limit(7).all()
    return render_template("statistics.html", t=t, lang=get_lang(), stats=stats)


@app.route("/plans")
def plans():
    t = get_t()
    return render_template("plans.html", t=t, lang=get_lang())


@app.route("/upgrade/<plan>")
@login_required
def upgrade(plan):
    if plan in ['free', 'pro', 'business']:
        current_user.plan = plan
        db.session.commit()
    return redirect("/plans")


# ─── ANALYZE API ──────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
@csrf.exempt
def analyze():
    lang = get_lang()
    t    = TRANSLATIONS[lang]

    # ── Rate limiting ──
    if current_user.is_authenticated:
        if not current_user.can_request():
            return jsonify({"error": t["limit_reached"], "score": 0})
        deep = current_user.deep_analysis
    else:
        anon_count = session.get("anon_requests", 0)
        if anon_count >= 3:
            return jsonify({"error": t["limit_reached"], "score": 0})
        session["anon_requests"] = anon_count + 1
        deep = False

    check_type = request.form.get("type", "text")
    text_input = request.form.get("text", "").strip()
    image      = request.files.get("image")

    try:
        # ── Call AI ──
        if image and image.filename:
            full_result = analyze_image_ai(image)
            check_type  = "image"
        elif check_type == "phone":
            full_result = analyze_phone_ai(text_input, lang)
        elif check_type == "link":
            full_result = analyze_link_ai(text_input, lang)
        else:
            full_result = analyze_text_ai(text_input, lang, deep)

        # ── Extract structured data ──
        score                    = extract_score(full_result)
        scam_type_code, scam_type_label = extract_scam_type(full_result, lang)
        triggers                 = extract_triggers(full_result)
        domain_trust             = extract_domain_trust(full_result)

        # All three language blocks — frontend switches without re-request
        results = {
            "kz": extract_language_block(full_result, "kz"),
            "ru": extract_language_block(full_result, "ru"),
            "en": extract_language_block(full_result, "en"),
        }
        result_block = results.get(lang) or results["kz"]

        level = "low" if score <= 30 else "medium" if score <= 65 else "high"

        update_stats(score, check_type)

        if current_user.is_authenticated:
            current_user.increment_requests()

        return jsonify({
            "result":          result_block,    # current lang (backward compat)
            "results":         results,          # {kz, ru, en} for live lang switch
            "score":           score,
            "level":           level,
            "scam_type":       scam_type_code,   # e.g. "PHISHING"
            "scam_type_label": scam_type_label,  # e.g. "Фишинг (жалған сайт/форма)"
            "triggers":        triggers,          # e.g. ["URGENCY","FEAR"]
            "domain_trust":    domain_trust,      # e.g. "FAKE_TRUST" (links only)
            "input":           text_input[:100] if text_input else "[image]",
        })

    except Exception as e:
        return jsonify({"error": f"❌ {str(e)}", "score": 0})


# ─── HOME ─────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    t    = get_t()
    lang = get_lang()
    requests_left = None
    if current_user.is_authenticated:
        today = str(date.today())
        if current_user.last_request_date != today:
            requests_left = current_user.get_daily_limit()
        else:
            requests_left = current_user.get_daily_limit() - current_user.requests_today
    return render_template("index.html", t=t, lang=lang, requests_left=requests_left)


# ─── INIT ─────────────────────────────────────────────────────────────────────

def create_tables():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin", email="admin@scamshield.kz",
                is_admin=True, plan='business', created_at=str(datetime.now())
            )
            admin.set_password("admin1234")
            db.session.add(admin)
            db.session.commit()


if __name__ == "__main__":
    create_tables()
    app.run(debug=True)