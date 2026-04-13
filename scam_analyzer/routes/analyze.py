import re
from flask import Blueprint, request, jsonify, session
from flask_login import current_user
from extensions import db, limiter
from translations import TRANSLATIONS, SCAM_TYPES
from services.ai import analyze_text, analyze_phone, analyze_link, analyze_image
from services.stats import update_stats

analyze_bp = Blueprint('analyze', __name__)

def get_lang():
    if current_user.is_authenticated:
        return current_user.language
    return session.get("lang", "kz")


def extract_score(text):
    if not text: return 0
    m = re.search(r'^SCORE:\s*(\d+)', text, re.MULTILINE)
    if m: return min(int(m.group(1)), 100)
    m = re.search(r'SCORE:\s*(\d+)', text, re.IGNORECASE)
    return min(int(m.group(1)), 100) if m else 0

def extract_scam_type(text, lang="kz"):
    if not text: return "UNKNOWN", "Белгісіз"
    m    = re.search(r'^SCAM_TYPE:\s*(\w+)', text, re.MULTILINE | re.IGNORECASE)
    code = m.group(1).upper() if m else "UNKNOWN"
    label = SCAM_TYPES.get(lang, SCAM_TYPES["kz"]).get(code, code)
    return code, label

def extract_triggers(text):
    if not text: return []
    m = re.search(r'^TRIGGERS:\s*([^\n]+)', text, re.MULTILINE)
    if not m: return []
    raw = m.group(1).strip()
    if raw.upper() in ["NONE", "ЖОҚ", "НЕТ", "-"]: return []
    return [x.strip() for x in raw.split(",") if x.strip()]

def extract_domain_trust(text):
    if not text: return None
    m = re.search(r'^DOMAIN_TRUST:\s*(\w+)', text, re.MULTILINE)
    return m.group(1).upper() if m else None

def extract_language_block(text, lang):
    if not text: return "❌ Жауап жоқ"
    markers = {"kz": ("KAZAKH:", "RUSSIAN:"),
               "ru": ("RUSSIAN:", "ENGLISH:"),
               "en": ("ENGLISH:", None)}
    start_tag, end_tag = markers.get(lang, ("KAZAKH:", "RUSSIAN:"))
    start = text.find(start_tag)
    if start == -1:
        cleaned = re.sub(r'(SCAM_TYPE|SCORE|TRIGGERS|DOMAIN_TRUST):.*\n?', '', text)
        return cleaned.strip().replace("\n", "<br>")
    end = text.find(end_tag, start + 1) if end_tag else len(text)
    if end == -1: end = len(text)
    block = text[start:end].strip()
    block = re.sub(r'SCORE:\s*\d+\n?', '', block)
    block = re.sub(r'SCAM_TYPE:\s*\S+\n?', '', block)
    block = re.sub(r'TRIGGERS:\s*[^\n]+\n?', '', block)
    block = re.sub(r'DOMAIN_TRUST:\s*\S+\n?', '', block)
    return block.strip().replace("\n", "<br>")


@analyze_bp.route("/analyze", methods=["POST"])
@limiter.limit("30 per minute")
def analyze():
    lang = get_lang()
    t    = TRANSLATIONS[lang]

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
        if image and image.filename:
            full_result = analyze_image(image)
            check_type  = "image"
        elif check_type == "phone":
            full_result = analyze_phone(text_input, lang)
        elif check_type == "link":
            full_result = analyze_link(text_input, lang)
        else:
            full_result = analyze_text(text_input, lang, deep)

        score                           = extract_score(full_result)
        scam_type_code, scam_type_label = extract_scam_type(full_result, lang)
        triggers                        = extract_triggers(full_result)
        domain_trust                    = extract_domain_trust(full_result)

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
            "result":          result_block,
            "results":         results,
            "score":           score,
            "level":           level,
            "scam_type":       scam_type_code,
            "scam_type_label": scam_type_label,
            "triggers":        triggers,
            "domain_trust":    domain_trust,
            "input":           text_input[:100] if text_input else "[image]",
        })
    except Exception as e:
        return jsonify({"error": f"❌ {str(e)}", "score": 0})