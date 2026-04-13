from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

class User(db.Model, UserMixin):
    id                = db.Column(db.Integer, primary_key=True)
    username          = db.Column(db.String(100), unique=True)
    email             = db.Column(db.String(200))
    password_hash     = db.Column(db.String(200))
    is_admin          = db.Column(db.Boolean, default=False)
    plan              = db.Column(db.String(20), default='free')
    requests_today    = db.Column(db.Integer, default=0)
    last_request_date = db.Column(db.String(20), default='')
    created_at        = db.Column(db.String(30), default='')
    theme             = db.Column(db.String(10), default='dark')
    notifications     = db.Column(db.Boolean, default=True)
    language          = db.Column(db.String(5), default='kz')
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))