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
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "scam_analyzer_secret_2024"

# DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

load_dotenv()

# ─── OPENROUTER CONFIG ────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemma-3n-e2b-it:free"

def call_openrouter(messages, max_tokens=1500):
    """Universal OpenRouter API call"""
    response = requests.post(
        url=OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://scamshield.kz",
            "X-Title": "ScamShield AI",
        },
        data=json.dumps({
            "model": OPENROUTER_MODEL,
            "max_tokens": max_tokens,
            "messages": messages
        }),
        timeout=30
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return content or "❌ Empty response from AI"

# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(200))
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    plan = db.Column(db.String(20), default='free')  # free, pro, business
    requests_today = db.Column(db.Integer, default=0)
    last_request_date = db.Column(db.String(20), default='')
    created_at = db.Column(db.String(30), default='')
    # Settings
    theme = db.Column(db.String(10), default='dark')
    notifications = db.Column(db.Boolean, default=True)
    language = db.Column(db.String(5), default='kz')
    deep_analysis = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_daily_limit(self):
        limits = {'free': 10, 'pro': 100, 'business': 999999}
        return limits.get(self.plan, 10)

    def can_request(self):
        today = str(date.today())
        if self.last_request_date != today:
            self.requests_today = 0
            self.last_request_date = today
            db.session.commit()
        return self.requests_today < self.get_daily_limit()

    def increment_requests(self):
        today = str(date.today())
        if self.last_request_date != today:
            self.requests_today = 0
            self.last_request_date = today
        self.requests_today += 1
        db.session.commit()


class DailyStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True)
    total_checks = db.Column(db.Integer, nullable=False, default=0)
    scam_detected = db.Column(db.Integer, nullable=False, default=0)
    safe_detected = db.Column(db.Integer, nullable=False, default=0)
    phone_checks = db.Column(db.Integer, nullable=False, default=0)
    link_checks = db.Column(db.Integer, nullable=False, default=0)
    text_checks = db.Column(db.Integer, nullable=False, default=0)


def update_stats(score, check_type='text'):
    today = str(date.today())
    stat = DailyStats.query.filter_by(date=today).first()
    if not stat:
        stat = DailyStats(
            date=today,
            total_checks=0,
            scam_detected=0,
            safe_detected=0,
            phone_checks=0,
            link_checks=0,
            text_checks=0
        )
        db.session.add(stat)
        db.session.flush()
    stat.total_checks = (stat.total_checks or 0) + 1
    if score >= 60:
        stat.scam_detected = (stat.scam_detected or 0) + 1
    else:
        stat.safe_detected = (stat.safe_detected or 0) + 1
    if check_type == 'phone':
        stat.phone_checks = (stat.phone_checks or 0) + 1
    elif check_type == 'link':
        stat.link_checks = (stat.link_checks or 0) + 1
    else:
        stat.text_checks = (stat.text_checks or 0) + 1
    db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── TRANSLATIONS ──────────────────────────────────────────────────────────────

T = {
    "kz": {
        "title": "ScamShield AI",
        "subtitle": "Алаяқтықты анықтаңыз",
        "new_chat": "Жаңа чат",
        "statistics": "Статистика",
        "phone_check": "Нөмірді тексеру",
        "link_check": "Сілтемені тексеру",
        "history": "Тарих",
        "plans": "Жоспарлар",
        "settings": "Параметрлер",
        "placeholder": "Хабарлама, нөмір немесе сілтемені енгізіңіз...",
        "login": "Кіру",
        "register": "Тіркелу",
        "logout": "Шығу",
        "profile": "Профиль",
        "username": "Пайдаланушы аты",
        "password": "Құпия сөз",
        "confirm_password": "Құпия сөзді растаңыз",
        "email": "Email",
        "today_checks": "Бүгін тексерілді",
        "scam_found": "Алаяқтық анықталды",
        "safe_found": "Қауіпсіз",
        "free_plan": "Тегін жоспар",
        "pro_plan": "Pro жоспары",
        "business_plan": "Бизнес жоспары",
        "requests_left": "сұраныс қалды",
        "dark_mode": "Түнгі режим",
        "light_mode": "Күндізгі режим",
        "notifications": "Хабарландырулар",
        "deep_analysis": "Терең анализ",
        "save_settings": "Сақтау",
        "risk_low": "Төмен қауіп",
        "risk_medium": "Орташа қауіп",
        "risk_high": "Жоғары қауіп",
        "analyzing": "Анализдеу...",
        "limit_reached": "Күнделікті лимит таусылды. Pro жоспарына өтіңіз.",
        "passwords_no_match": "Құпия сөздер сәйкес емес",
        "user_exists": "Бұл пайдаланушы аты бос емес",
        "login_error": "Қате логин немесе құпия сөз",
        "welcome": "Қош келдіңіз",
        "send": "Жіберу",
        "chat_title": "Жаңа чат",
        "no_history": "Тарих жоқ",
        "monthly": "айына",
        "per_req": "сұраныс/күн",
        "unlimited": "Шексіз",
    },
    "ru": {
        "title": "ScamShield AI",
        "subtitle": "Определите мошенничество",
        "new_chat": "Новый чат",
        "statistics": "Статистика",
        "phone_check": "Проверка номера",
        "link_check": "Проверка ссылки",
        "history": "История",
        "plans": "Планы",
        "settings": "Параметры",
        "placeholder": "Введите сообщение, номер или ссылку...",
        "login": "Войти",
        "register": "Регистрация",
        "logout": "Выйти",
        "profile": "Профиль",
        "username": "Имя пользователя",
        "password": "Пароль",
        "confirm_password": "Подтвердите пароль",
        "email": "Email",
        "today_checks": "Проверено сегодня",
        "scam_found": "Обнаружено мошенничеств",
        "safe_found": "Безопасных",
        "free_plan": "Бесплатный план",
        "pro_plan": "Pro план",
        "business_plan": "Бизнес план",
        "requests_left": "запросов осталось",
        "dark_mode": "Тёмный режим",
        "light_mode": "Светлый режим",
        "notifications": "Уведомления",
        "deep_analysis": "Глубокий анализ",
        "save_settings": "Сохранить",
        "risk_low": "Низкий риск",
        "risk_medium": "Средний риск",
        "risk_high": "Высокий риск",
        "analyzing": "Анализирую...",
        "limit_reached": "Дневной лимит исчерпан. Перейдите на Pro план.",
        "passwords_no_match": "Пароли не совпадают",
        "user_exists": "Это имя пользователя занято",
        "login_error": "Неверный логин или пароль",
        "welcome": "Добро пожаловать",
        "send": "Отправить",
        "chat_title": "Новый чат",
        "no_history": "История пуста",
        "monthly": "в месяц",
        "per_req": "запросов/день",
        "unlimited": "Безлимит",
    },
    "en": {
        "title": "ScamShield AI",
        "subtitle": "Detect scams instantly",
        "new_chat": "New chat",
        "statistics": "Statistics",
        "phone_check": "Phone check",
        "link_check": "Link check",
        "history": "History",
        "plans": "Plans",
        "settings": "Settings",
        "placeholder": "Enter message, phone number or link...",
        "login": "Login",
        "register": "Register",
        "logout": "Logout",
        "profile": "Profile",
        "username": "Username",
        "password": "Password",
        "confirm_password": "Confirm password",
        "email": "Email",
        "today_checks": "Checked today",
        "scam_found": "Scams detected",
        "safe_found": "Safe",
        "free_plan": "Free plan",
        "pro_plan": "Pro plan",
        "business_plan": "Business plan",
        "requests_left": "requests left",
        "dark_mode": "Dark mode",
        "light_mode": "Light mode",
        "notifications": "Notifications",
        "deep_analysis": "Deep analysis",
        "save_settings": "Save",
        "risk_low": "Low risk",
        "risk_medium": "Medium risk",
        "risk_high": "High risk",
        "analyzing": "Analyzing...",
        "limit_reached": "Daily limit reached. Upgrade to Pro.",
        "passwords_no_match": "Passwords don't match",
        "user_exists": "Username already taken",
        "login_error": "Invalid username or password",
        "welcome": "Welcome",
        "send": "Send",
        "chat_title": "New chat",
        "no_history": "No history",
        "monthly": "per month",
        "per_req": "requests/day",
        "unlimited": "Unlimited",
    }
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_lang():
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")

def get_t():
    return T[get_lang()]

def extract_score(text):
    if not text:
        return 0
    match = re.search(r'SCORE:\s*(\d+)', text, re.IGNORECASE)
    if match:
        return min(int(match.group(1)), 100)
    match = re.search(r'(\d+)\s*/\s*(\d+)', text)
    if match:
        a, b = int(match.group(1)), int(match.group(2))
        if b > 0:
            return min(int(a/b*100), 100)
    return 0

def analyze_text_ai(text, lang, deep=False):
    depth = "Provide detailed multi-paragraph analysis with" if deep else "Provide concise analysis with"
    prompt = f"""You are a scam detection AI. Analyze this message/text for signs of fraud, phishing, or scam.

{depth} key points only.

Respond ONLY in this exact format (no markdown, no extra text):
KAZAKH:
Қауіп деңгейі: [Төмен/Орташа/Жоғары]
SCORE: [0-100]
Себептер:
- [reason 1]
- [reason 2]
Кеңес:
- [advice 1]

RUSSIAN:
Уровень риска: [Низкий/Средний/Высокий]
SCORE: [0-100]
Причины:
- [reason 1]
Совет:
- [advice 1]

ENGLISH:
Risk level: [Low/Medium/High]
SCORE: [0-100]
Reasons:
- [reason 1]
Advice:
- [advice 1]

Text to analyze:
{text}"""
    return call_openrouter([{"role": "user", "content": prompt}])

def analyze_phone_ai(phone, lang):
    prompt = f"""You are a scam detection AI. Check this phone number for scam reports.

Respond ONLY in this format:
KAZAKH:
Нөмір: {phone}
Қауіп деңгейі: [Төмен/Орташа/Жоғары]
SCORE: [0-100]
Ақпарат:
- [info]
Кеңес:
- [advice]

RUSSIAN:
Номер: {phone}
Уровень риска: [Низкий/Средний/Высокий]
SCORE: [0-100]
Информация:
- [info]
Совет:
- [advice]

ENGLISH:
Number: {phone}
Risk level: [Low/Medium/High]
SCORE: [0-100]
Info:
- [info]
Advice:
- [advice]

Phone: {phone}"""
    return call_openrouter([{"role": "user", "content": prompt}])

def analyze_link_ai(link, lang):
    prompt = f"""You are a scam detection AI. Analyze this URL/link for phishing or scam.

Respond ONLY in this format:
KAZAKH:
Сілтеме: {link}
Қауіп деңгейі: [Төмен/Орташа/Жоғары]
SCORE: [0-100]
Анализ:
- [finding]
Кеңес:
- [advice]

RUSSIAN:
Ссылка: {link}
Уровень риска: [Низкий/Средний/Высокий]
SCORE: [0-100]
Анализ:
- [finding]
Совет:
- [advice]

ENGLISH:
Link: {link}
Risk level: [Low/Medium/High]
SCORE: [0-100]
Analysis:
- [finding]
Advice:
- [advice]

Link: {link}"""
    return call_openrouter([{"role": "user", "content": prompt}])

def analyze_image_ai(file):
    """Convert image to base64 and send to OpenRouter vision model"""
    image = Image.open(file)
    # Convert to JPEG for smaller size
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = """Analyze this image for scam indicators.
Respond in this format:
KAZAKH:
Қауіп деңгейі: [Төмен/Орташа/Жоғары]
SCORE: [0-100]
Себептер:
- [...]
Кеңес:
- [...]

RUSSIAN:
Уровень риска: [Низкий/Средний/Высокий]
SCORE: [0-100]
Причины:
- [...]
Совет:
- [...]

ENGLISH:
Risk level: [Low/Medium/High]
SCORE: [0-100]
Reasons:
- [...]
Advice:
- [...]"""

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]
    }]
    # Use a vision-capable model for images
    response = requests.post(
        url=OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://scamshield.kz",
            "X-Title": "ScamShield AI",
        },
        data=json.dumps({
            "model": "google/gemini-flash-1.5-8b",  # free vision model
            "max_tokens": 1000,
            "messages": messages
        }),
        timeout=30
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def extract_language_block(text, lang):
    if not text:
        return "❌ No response from AI"
    if lang == "kz":
        start = text.find("KAZAKH:")
        end = text.find("RUSSIAN:")
    elif lang == "ru":
        start = text.find("RUSSIAN:")
        end = text.find("ENGLISH:")
    else:
        start = text.find("ENGLISH:")
        end = len(text)
    if start == -1:
        return text.replace("\n", "<br>")
    block = text[start:end].strip()
    block = re.sub(r'SCORE:\s*\d+\n?', '', block)
    return block.replace("\n", "<br>")

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
        confirm = request.form.get("confirm_password", "")
        email = request.form.get("email", "")
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
        current_user.theme = request.form.get("theme", "dark")
        current_user.notifications = "notifications" in request.form
        current_user.deep_analysis = "deep_analysis" in request.form
        db.session.commit()
        return redirect("/settings")
    return render_template("settings.html", t=t, lang=get_lang(), user=current_user)


@app.route("/statistics")
def statistics():
    t = get_t()
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
def analyze():
    lang = get_lang()
    t = T[lang]

    # Check limit for logged-in users
    if current_user.is_authenticated:
        if not current_user.can_request():
            return jsonify({"error": t["limit_reached"], "score": 0})
        deep = current_user.deep_analysis
    else:
        # Anonymous: 3 requests tracked in session
        anon_count = session.get("anon_requests", 0)
        if anon_count >= 3:
            return jsonify({"error": t["limit_reached"], "score": 0})
        session["anon_requests"] = anon_count + 1
        deep = False

    check_type = request.form.get("type", "text")
    text_input = request.form.get("text", "").strip()
    image = request.files.get("image")

    try:
        if image and image.filename:
            full_result = analyze_image_ai(image)
            check_type = "image"
        elif check_type == "phone":
            full_result = analyze_phone_ai(text_input, lang)
        elif check_type == "link":
            full_result = analyze_link_ai(text_input, lang)
        else:
            full_result = analyze_text_ai(text_input, lang, deep)

        score = extract_score(full_result)
        result_block = extract_language_block(full_result, lang)

        if score <= 30:
            level = "low"
        elif score <= 65:
            level = "medium"
        else:
            level = "high"

        update_stats(score, check_type)

        if current_user.is_authenticated:
            current_user.increment_requests()

        return jsonify({
            "result": result_block,
            "score": score,
            "level": level,
            "input": text_input[:100] if text_input else "[image]"
        })

    except Exception as e:
        return jsonify({"error": f"❌ {str(e)}", "score": 0})


# ─── MAIN ──────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    t = get_t()
    lang = get_lang()
    requests_left = None
    if current_user.is_authenticated:
        today = str(date.today())
        if current_user.last_request_date != today:
            requests_left = current_user.get_daily_limit()
        else:
            requests_left = current_user.get_daily_limit() - current_user.requests_today
    return render_template("index.html", t=t, lang=lang, requests_left=requests_left)


def create_tables():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", email="admin@scamshield.kz",
                        is_admin=True, plan='business', created_at=str(datetime.now()))
            admin.set_password("admin1234")
            db.session.add(admin)
            db.session.commit()


if __name__ == "__main__":
    create_tables()
    app.run(debug=True)
