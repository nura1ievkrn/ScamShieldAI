from flask import Blueprint, render_template, request, redirect, session
from flask_login import login_user, logout_user, login_required
from extensions import db, limiter
from models import User
from translations import TRANSLATIONS
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

MIN_PASSWORD_LENGTH = 8

def get_lang():
    from flask_login import current_user
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")

def get_t():
    return TRANSLATIONS[get_lang()]


@auth_bp.route("/set_language/<lang>")
def set_language(lang):
    if lang in ['kz', 'ru', 'en']:
        session["lang"] = lang
        from flask_login import current_user
        if current_user.is_authenticated:
            current_user.language = lang
            db.session.commit()
    return redirect(request.referrer or "/")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    t = get_t()
    lang = get_lang()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        email    = request.form.get("email", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            error = {
                'kz': f'Құпия сөз кемінде {MIN_PASSWORD_LENGTH} символ болуы керек',
                'ru': f'Пароль должен быть не менее {MIN_PASSWORD_LENGTH} символов',
                'en': f'Password must be at least {MIN_PASSWORD_LENGTH} characters',
            }.get(lang)
        elif password != confirm:
            error = t["passwords_no_match"]
        elif User.query.filter_by(username=username).first():
            error = t["user_exists"]
        else:
            user = User(username=username, email=email,
                        created_at=str(datetime.now()))
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect("/")
    return render_template("register.html", t=t, lang=lang, error=error)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    t = get_t()
    lang = get_lang()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect("/")
        error = t["login_error"]
    return render_template("login.html", t=t, lang=lang, error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")