from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "scam_analyzer_secret_2024")

# ── DATABASE ──────────────────────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── SECURITY ──────────────────────────────────────────────────────────────────
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# app.config['SESSION_COOKIE_SECURE'] = True  # включить при HTTPS

# ── EXTENSIONS ────────────────────────────────────────────────────────────────
from extensions import db, login_manager, csrf, limiter

db.init_app(app)
login_manager.init_app(app)
csrf.init_app(app)
limiter.init_app(app)

login_manager.login_view = "auth.login"

# ── BLUEPRINTS ────────────────────────────────────────────────────────────────
from routes.auth    import auth_bp
from routes.analyze import analyze_bp
from routes.pages   import pages_bp

app.register_blueprint(auth_bp)
app.register_blueprint(analyze_bp)
app.register_blueprint(pages_bp)

# ── ERROR HANDLERS ────────────────────────────────────────────────────────────
from flask import request, jsonify, render_template
from flask_wtf.csrf import CSRFError

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template("login.html",
                           t=_get_t(), lang=_get_lang(),
                           error="Сессия устарела. Повторите попытку."), 400

@app.errorhandler(429)
def handle_rate_limit(e):
    msg = {
        'kz': 'Тым көп сұраныс. Біраз күтіңіз.',
        'ru': 'Слишком много запросов. Подождите немного.',
        'en': 'Too many requests. Please wait.',
    }
    lang = _get_lang()
    if request.path == '/analyze':
        return jsonify({"error": msg.get(lang, msg['en']), "score": 0}), 429
    return render_template("login.html",
                           t=_get_t(), lang=lang,
                           error=msg.get(lang, msg['en'])), 429

def _get_lang():
    from flask import session
    from flask_login import current_user
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")

def _get_t():
    from translations import TRANSLATIONS
    return TRANSLATIONS[_get_lang()]

# ── INIT ──────────────────────────────────────────────────────────────────────
def create_tables():
    with app.app_context():
        db.create_all()
        from models import User
        from datetime import datetime
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin", email="admin@scamshield.kz",
                is_admin=True, plan='business',
                created_at=str(datetime.now())
            )
            admin.set_password("admin1234")
            db.session.add(admin)
            db.session.commit()

if __name__ == "__main__":
    create_tables()
    app.run(debug=True)