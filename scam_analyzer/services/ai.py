import os
import json
import base64
import requests
from io import BytesIO
from PIL import Image

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"

FREE_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-3n-e2b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-0.6b:free",
    "microsoft/phi-3-mini-128k-instruct:free",
]

VISION_MODELS = [
    "openrouter/free",
    "google/gemma-3n-e4b-it:free",
    "google/gemma-3n-e2b-it:free",
    "stepfun/step-3.5-flash:free",
    "minimax/minimax-m2.5:free",
]

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


def call_openrouter(messages, max_tokens=900, system_prompt=None):
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

    return f"❌ Барлық модельдер қол жетімді емес. ({last_error})"


def analyze_text(text, lang, deep=False):
    extra = " Give 3-4 bullet points per section." if deep else " Give 2-3 bullet points per section."
    user_msg = (
        f"Analyze this text for scam signs.{extra}\n\n"
        f"Real Kazakhstan scam patterns:\n"
        f"1. 'Ваш счёт взломан, переведите на защищённый счёт' → IMPERSONATION\n"
        f"2. 'Работа на дому 500$/день, предоплата за обучение' → JOB_SCAM\n"
        f"3. 'Ваш Kaspi заблокирован, назовите код из SMS' → PHISHING\n"
        f"4. 'Вы выиграли iPhone, оплатите доставку' → LOTTERY_SCAM\n"
        f"5. 'Инвестируй 50000₸ → получи 200000₸ за 3 дня' → FINANCIAL_PYRAMID\n\n"
        f"Text:\n\"\"\"{text}\"\"\""
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=800, system_prompt=SYSTEM_PROMPT,
    )


def analyze_phone(phone, lang):
    user_msg = (
        f"Analyze this Kazakhstan phone number for scam risk: {phone}\n\n"
        f"Risk patterns:\n"
        f"- +7700/708/747 = prepaid SIM often used by scammers\n"
        f"- Real bank lines: Kaspi=7272, Halyk=7077, BCC=7010\n"
        f"- Foreign numbers (+44,+1,+380) spoofed as local = HIGH risk\n"
        f"Emergency contacts if scam: 102, cybercrime.kz"
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=700, system_prompt=SYSTEM_PROMPT,
    )


def analyze_link(link, lang):
    user_msg = (
        f"Analyze this URL for phishing targeting Kazakhstan users: {link}\n\n"
        f"Trusted domains: kaspi.kz, halykbank.kz, egov.kz, enpf.kz\n"
        f"Known fake domains: kaspi-kz.com, halyk-bank.net, egov-kz.org\n"
        f"High-risk TLDs: .xyz .top .tk .ml .click .cf\n"
        f"Add DOMAIN_TRUST: [HIGH_TRUST/MEDIUM_TRUST/LOW_TRUST/NO_TRUST/FAKE_TRUST] after TRIGGERS line."
    )
    return call_openrouter(
        [{"role": "user", "content": user_msg}],
        max_tokens=700, system_prompt=SYSTEM_PROMPT,
    )


def analyze_image(file):
    image  = Image.open(file)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = (
        SYSTEM_PROMPT
        + "\n\nAnalyze this image for scam/fraud in Kazakhstan context.\n"
        "Look for: fake Kaspi/Halyk screenshots, fake prizes, fake job offers, "
        "suspicious QR codes, phishing pages, fake receipts."
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