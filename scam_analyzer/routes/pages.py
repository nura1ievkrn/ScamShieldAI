from flask import Blueprint, render_template, request, redirect, session
from flask_login import login_required, current_user
from extensions import db
from models import DailyStats
from translations import TRANSLATIONS
from datetime import date

pages_bp = Blueprint('pages', __name__)

def get_lang():
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")

def get_t():
    return TRANSLATIONS[get_lang()]


@pages_bp.route("/")
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


@pages_bp.route("/statistics")
def statistics():
    t     = get_t()
    stats = DailyStats.query.order_by(DailyStats.date.desc()).limit(7).all()
    return render_template("statistics.html", t=t, lang=get_lang(), stats=stats)


@pages_bp.route("/plans")
def plans():
    return render_template("plans.html", t=get_t(), lang=get_lang())


@pages_bp.route("/upgrade/<plan>")
@login_required
def upgrade(plan):
    if plan in ['free', 'pro', 'business']:
        current_user.plan = plan
        db.session.commit()
    return redirect("/plans")


@pages_bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", t=get_t(), lang=get_lang(), user=current_user)


@pages_bp.route("/settings", methods=["GET", "POST"])
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