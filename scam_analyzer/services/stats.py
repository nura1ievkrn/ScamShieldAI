from datetime import date
from extensions import db
from models import DailyStats


def update_stats(score, check_type='text'):
    today = str(date.today())
    stat  = DailyStats.query.filter_by(date=today).first()
    if not stat:
        stat = DailyStats(date=today, total_checks=0, scam_detected=0,
                          safe_detected=0, phone_checks=0,
                          link_checks=0, text_checks=0)
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