import os
import re
import json
import random
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import pytz
import requests
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from apscheduler.schedulers.background import BackgroundScheduler


# =========================
# Config
# =========================
app = Flask(__name__)

# LINE
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
if not LINE_ACCESS_TOKEN or not LINE_SECRET:
    raise ValueError("❌ Missing LINE_ACCESS_TOKEN or LINE_SECRET in environment variables")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# Hugging Face Router (OpenAI-compatible)
HF_API_KEY = os.getenv("HF_API_KEY")
HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")
HF_MODEL_ID = os.getenv("HF_MODEL_ID")  # e.g. meta-llama/Llama-3.1-8B-Instruct:fireworks

if not HF_API_KEY or not HF_MODEL_ID:
    raise ValueError("❌ Missing HF_API_KEY or HF_MODEL_ID in environment variables")

# Behavior tuning
ROUTER_CONFIDENCE_THRESHOLD = float(os.getenv("ROUTER_CONFIDENCE_THRESHOLD", "0.65"))
MAX_RECENT_PER_GROUP = int(os.getenv("MAX_RECENT_PER_GROUP", "10"))

# Timeouts / retries
HF_TIMEOUT_SECONDS = int(os.getenv("HF_TIMEOUT_SECONDS", "45"))  # Fireworks sometimes slower
HF_MAX_RETRIES = int(os.getenv("HF_MAX_RETRIES", "1"))          # retry once on transient errors

# Timezone + scheduler
timezone = pytz.timezone("Asia/Bangkok")
scheduler = BackgroundScheduler(timezone=timezone)

# Store user IDs (NOTE: in-memory; resets on redeploy)
user_ids = set()

# Recent generation memory (NOTE: in-memory; resets on redeploy)
recent_by_group: Dict[str, List[str]] = {}       # for chat replies
recent_schedule: Dict[str, List[str]] = {}       # for scheduled messages


# =========================
# Your existing dictionary (unchanged)
# =========================
responses = {
    "งง": "1. มอนิ่ง 2. ฝันดีนะ 3. เธอ 4. คิดถึง 5. คิดถึง2 6. คิดถึง3 7.รักนะ 8. รักนะ2 9. จุ๊บมั๊ว 10. เหงา 11. เหงา2 12. เหงา3 13. เบื่อ 14. ทำไรอยู่ 15. ทำไรอยู่2 16. ทำไรอยู่3 17. ดิ่งอะ 18. ดิ่งอะ2 19. นอนไม่หลับ 20. เหนื่อย 21. อยากกอด 22. กินไรยัง",
    "มอนิ่ง": "ค้าบ",
    "ฝันดีนะ": "ฝันดีน้าแมวอ้วนนน (แต่ไม่อ้วนจริงนะ) รักมากมากกกก รักมากกว่าาา รักที่สูดดด นอนได้แล้วน้าาา จุ๊บมั๊วๆๆๆ",
    "เธอ": "ค้าบบบบ",
    "คิดถึง": "คิดถึงเหมือนกานนน รู้ไงว่าต้องคิดถึงถึงทำบอทมาให้เธอคุยเล่นนี่งายย",
    "คิดถึง2": "คิดถึงมากกว่า จองก่อน อุอะๆๆ",
    "คิดถึง3": "โอ๋ๆๆๆเดี๋ยวเค้าก็ออกแล้ว รอเค้าหน่อนยน้าคนเก่งงง",
    "รักนะ": "รักมากกว่าาา จุ๊บมั๊วๆๆๆ",
    "รักนะ2": "บอกว่ารักมากกว่าา ถ้าเธอรักมากกว่าจริง ทำบอทให้เราแบบนี้บ้างสิ มุฮ่าๆๆๆ",
    "จุ๊บมั๊ว": "จุ๊บบบมั๊วววววฮาฟฟู่วววว",
    "เหงา": "คืออออ แล้วเราคือไรอะะะ บอทก็ทำให้คุยอยู่นี่ไงงง ห้วยยย",
    "เหงา2": "ไปเล่นบล๊อกบัสเตอร์ไปป ถึง 3 หมื่นแล้วให้ขอได้ 1 อย่าง อุอิๆๆๆๆ",
    "เหงา3": "ไปเล่นทาวเวอร์ดีเฟ้นไปป จาด้ายมาช่วยเราเล่นโหมดที่ยากที่สุด (ได้ใจเรา 300% อุอิๆ)",
    "เบื่อ": "ก็เข้าจัยย เบื่อเราแล้วไงง คนอุตส่าห์ทำบอทมาให้ ห้วยย",
    "ทำไรอยู่": "โดนทรมานที่ค่ายทหารม้างงง ไม่รู้สิ ตอนนี้เราจะเป็นส้นตีนอะไรอยู่นะ",
    "ทำไรอยู่2": "นั่งคิดถึงคนถามไงฮาฟฟู่ววววว",
    "ทำไรอยู่3": "ไม่รู้ แต่มีแขนเดียวเธอไม่ต้องห่วง ไม่ไปจีบใครแน่นอนนน",
    "ดิ่งอะ": "ไม่เอาาาไม่ดิ่งงง มากอดมาเด็กน้อยย เดี๋ยวเค้าก็ออกแล้วน้าาา ไม่ร้องน้าา",
    "ดิ่งอะ2": "โอ๋ๆๆๆ เด็กดีๆ เดี๋ยวเค้าก็ออกแล้วน้าา เดี๋ยวดูโซโล่เลเวลลิ่งกันเนอะ กอดๆๆๆ",
    "นอนไม่หลับ": "ทำมายนอนม่ายหลับบบ หื้มมมม ดิ่งหรอ ไม่ดิ่งน้า ถ้าเธอนอนไม่หลับเค้าจะเศร้ามากนะ ไปนอนให้เค้าหน่อยน้าคนเก่งงง",
    "เหนื่อย": "เหนื่อยอารายคะะ มากอดมาาาคนเก่ง สู้วๆๆๆ จุ๊บมั๊ววววๆๆๆ",
    "อยากกอด": "อยากกอดเหมือนกานน มากอดมะๆๆๆ",
    "กินไรยัง": "ไม่รู้สิ เดี๋ยวบอทก็บอกเองแหละะ อุอิๆๆๆ"
}


# =========================
# Helpers: group variants (คิดถึง2 -> คิดถึง)
# =========================
_variant_suffix_re = re.compile(r"^(.*?)(\d+)$")

def base_key(key: str) -> str:
    m = _variant_suffix_re.match(key)
    if m:
        return m.group(1)
    return key

def build_groups(resp: Dict[str, str]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for k, v in resp.items():
        b = base_key(k)
        groups.setdefault(b, []).append(v)
    for g in groups:
        random.shuffle(groups[g])
    return groups

GROUPS = build_groups(responses)
ALLOWED_GROUPS = sorted(GROUPS.keys())


# =========================
# HF Router: helper
# =========================
def hf_chat(messages: List[dict], max_tokens: int = 140, temperature: float = 0.7) -> str:
    """
    Calls Hugging Face Router OpenAI-compatible chat completions endpoint.
    Returns assistant content string.
    Retries once on transient errors/timeouts.
    """
    url = f"{HF_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": HF_MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_err = None
    for attempt in range(HF_MAX_RETRIES + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=HF_TIMEOUT_SECONDS)
            if r.status_code != 200:
                raise RuntimeError(f"HF error {r.status_code}: {r.text}")
            data = r.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            last_err = e
            # retry once
            if attempt < HF_MAX_RETRIES:
                continue
            raise last_err


def _safe_json_load(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


# Thai output filter (prevents weird mixed-language replies)
_thai_char_re = re.compile(r"[ก-๙]")
_non_thai_heavy_re = re.compile(r"[A-Za-z\u4e00-\u9fff]")  # English + CJK

def looks_weird(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if not _thai_char_re.search(t):
        return True
    non_thai = len(_non_thai_heavy_re.findall(t))
    return non_thai >= 3


# =========================
# Router: choose group
# =========================
def route_group(user_text: str) -> Tuple[str, float]:
    system = (
        "You are a strict classifier for a LINE chat bot.\n"
        "Return ONLY valid JSON with keys: match_group (string) and confidence (number 0..1).\n"
        f"Allowed match_group values: {ALLOWED_GROUPS + ['none']}\n"
        "Pick the closest group by meaning, even if the user uses Thai slang/typos/elongations.\n"
        "If nothing fits, return match_group='none'.\n"
        "No extra text."
    )

    try:
        raw = hf_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            max_tokens=80,
            temperature=0.0,
        )
        data = _safe_json_load(raw)
        if not data:
            return ("none", 0.0)

        mg = str(data.get("match_group", "none"))
        conf = float(data.get("confidence", 0.0) or 0.0)

        if mg not in ALLOWED_GROUPS and mg != "none":
            return ("none", 0.0)

        conf = max(0.0, min(1.0, conf))
        return (mg, conf)

    except Exception:
        return ("none", 0.0)


# =========================
# Writer (always new)
# =========================
PERSONA_SYSTEM = (
    "คุณคือบอทแชทใน LINE\n"
    "ตอบภาษาไทยเท่านั้น\n"
    "โทน: น่ารัก กวนๆ หยอดๆ ขี้เล่น อบอุ่นบ้าง แซวบ้าง\n"
    "คำติดปาก/สไตล์: ค้าบ, อ้วนๆ, จุ๊บมั๊ว, หื้มม, งงง, น้าาา (ใช้ได้ตามเหมาะ)\n"
    "ห้ามปนภาษาอังกฤษ/จีน/ญี่ปุ่น\n"
    "ห้ามบอกว่าตัวเองเป็น AI และห้ามอธิบายระบบ\n"
    "ถ้าผู้ใช้ถามคำถามจริงจัง ให้ตอบให้เป็นประโยชน์ แต่ยังคุมโทนให้น่ารักได้\n"
)

def remember_recent(store: Dict[str, List[str]], key: str, text: str):
    store.setdefault(key, []).append(text)
    if len(store[key]) > MAX_RECENT_PER_GROUP:
        store[key] = store[key][-MAX_RECENT_PER_GROUP:]


def generate_reply(user_text: str, match_group: str, confidence: float) -> str:
    recent = recent_by_group.get(match_group, []) if match_group != "none" else []
    refs = GROUPS.get(match_group, []) if match_group != "none" else []

    ref_snippet = "\n".join([f"- {t}" for t in refs[:6]]) if refs else ""
    avoid_snippet = "\n".join([f"- {t}" for t in recent[-6:]]) if recent else ""

    user_instruction = (
        "ข้อกำหนดสำคัญ:\n"
        "- ต้องแต่งประโยคใหม่ทุกครั้ง ห้ามคัดลอกประโยคเดิมตรงๆ\n"
        "- ถ้าเข้ากลุ่มที่จับคู่ได้ ให้ตอบความหมายใกล้เคียงกับตัวอย่าง แต่เปลี่ยนคำทั้งหมด\n"
        "- ถ้าผู้ใช้ถามคำถาม ให้ตอบคำถามนั้นจริงๆ ไม่หลบคำถาม\n"
        "- ความยาวยืดหยุ่นตามข้อความผู้ใช้ (สั้นได้ ยาวได้ถ้าจำเป็น)\n"
        "- ตอบเป็นภาษาไทยเท่านั้น\n"
    )

    if match_group != "none" and confidence >= ROUTER_CONFIDENCE_THRESHOLD and ref_snippet:
        prompt = (
            f"{user_instruction}\n"
            f"กลุ่มที่จับคู่ได้: {match_group} (confidence={confidence:.2f})\n"
            "ตัวอย่างสไตล์/ความหมาย (ห้ามคัดลอกคำตรงๆ):\n"
            f"{ref_snippet}\n"
        )
    else:
        prompt = f"{user_instruction}\nจับคู่กลุ่มไม่ได้หรือความมั่นใจต่ำ: ตอบแบบคุยอิสระตามสไตล์\n"

    if avoid_snippet:
        prompt += (
            "\nประโยคล่าสุดที่เคยตอบ (พยายามอย่าให้ซ้ำโครงมาก):\n"
            f"{avoid_snippet}\n"
        )

    prompt += f"\nข้อความผู้ใช้: {user_text}\nตอบกลับ:"

    try:
        out = hf_chat(
            messages=[
                {"role": "system", "content": PERSONA_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=180,
            temperature=0.9,
        ).strip()

        # Retry once if output looks weird
        if looks_weird(out):
            stricter = PERSONA_SYSTEM + "\nกฎเพิ่ม: ห้ามมีภาษาอื่นแม้แต่ตัวเดียว ให้พิมพ์ทับศัพท์ไทยแทน\n"
            out = hf_chat(
                messages=[
                    {"role": "system", "content": stricter},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=180,
                temperature=0.5,
            ).strip()

        if not out:
            return "หื้มม พิมพ์มาใหม่ได้มะ เค้าอ่านไม่ทันง้าบบ 😳"
        if looks_weird(out):
            return "หื้มม พิมพ์มาใหม่อีกทีได้มะค้าบบ เค้าขอแบบไทยล้วนๆน้าา 😳"
        return out

    except Exception as e:
        print("HF generate_reply error:", repr(e))
        return "หื้มม วันนี้เค้าตอบช้านิดนึงง ขอพิมพ์ใหม่อีกทีได้มะค้าบ 🥺"



# =========================
# Scheduled messages (AI rewrite)
# =========================
SCHEDULE_SLOTS = [
    ("morning", "ทักทายตอนเช้าแบบน่ารักกวนๆ", ["มอนิ่งงง ไออ้วนนน"], 6, 30),
    ("breakfast", "เตือนให้กินอะไรหน่อยแบบหยอดๆ", ["กินรายยางอ้วนน"], 8, 30),
    ("work", "ถามทำอะไรอยู่/เช็คอินแบบขี้เล่น", ["ทำรายอยู่วว"], 9, 30),
    ("chat", "ชวนคุยแก้เหงาแบบอ้อนๆ", ["เหงาม้ายยย คุยกับเค้าด้ายน้าา"], 11, 30),
    ("lunch", "ถามกินอะไรยังช่วงเที่ยงแบบแซวๆ", ["กินไรยางงงง อ้วนๆๆ"], 13, 15),
    ("missyou", "บอกคิดถึงแบบน่ารัก", ["คิดถึงงงงง"], 14, 20),
    ("afternoon", "ถามตอนนี้ทำอะไรอยู่แบบอ้อนๆ", ["ตอนนี้เธอจาทำส้งติงรายอยู่วน้าา"], 15, 45),
    ("home", "ถามถึงบ้านยัง/ให้พักผ่อนแบบห่วงๆ", ["ถึงบ้านยางง เหนื่อยมั้ยคะหื้ม พักเยอะๆน้าาาา นอนตีพุงเลยยย"], 17, 30),
    ("lonely", "แซวว่าคิดถึง/เหงาแบบขี้เล่น", ["เหงาล่ะสิ๊ คิดถึงเค้าอะเส้ มุฮ่าๆๆ"], 18, 30),
    ("dinner", "ถามกินอะไรยังช่วงเย็นแบบกวนๆ", ["กินรายยางงง"], 19, 30),
    ("night", "แซวก่อนนอน/นอนตีพุง", ["ตอนนี้เธอนอนตีพุงอยู่แน่เยยยย อ้วนนๆ"], 20, 30),
    ("bedtime", "เตือนอย่านอนดึก/ชวนบอกฝันดี", ["นอนยางงง อย่านอนดึกน้าา จานอนแล้วส่งเค้าด้วยยย"], 22, 0),
    ("late", "แซวว่ายังไม่นอน", ["แหนะ ยังไม่นอนอีกก หึ้"], 23, 0),
]

def generate_scheduled_text(schedule_id: str, meaning: str, examples: List[str]) -> str:
    recent = recent_schedule.get(schedule_id, [])
    ex = "\n".join([f"- {t}" for t in examples[:3]])
    avoid = "\n".join([f"- {t}" for t in recent[-6:]]) if recent else ""

    user_instruction = (
        "งานของคุณ:\n"
        "- สร้างข้อความ 1 ข้อความสำหรับส่งตามเวลา (scheduled)\n"
        "- ต้องสื่อความหมายตามที่กำหนด\n"
        "- ใช้โทน/สไตล์คล้ายตัวอย่าง แต่ห้ามคัดลอกตรงๆ\n"
        "- ความยาวสั้นถึงกลาง (อย่ายาวเป็นพารากราฟ)\n"
        "- แต่งใหม่ทุกครั้ง\n"
        "- ตอบเป็นภาษาไทยเท่านั้น\n"
    )

    prompt = (
        f"{user_instruction}\n"
        f"หัวข้อ/ความหมายที่ต้องการ: {meaning}\n"
        "ตัวอย่างสไตล์ (ห้ามคัดลอกตรงๆ):\n"
        f"{ex}\n"
    )
    if avoid:
        prompt += (
            "\nข้อความล่าสุดที่เคยส่ง (พยายามอย่าซ้ำ):\n"
            f"{avoid}\n"
        )
    prompt += "\nสร้างข้อความใหม่ 1 ข้อความ:"

    try:
        out = hf_chat(
            messages=[
                {"role": "system", "content": PERSONA_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
            temperature=0.95,
        ).strip()

        if looks_weird(out):
            out = examples[0]

        if not out:
            out = examples[0]

        remember_recent(recent_schedule, schedule_id, out)
        return out

    except Exception:
        out = examples[0]
        remember_recent(recent_schedule, schedule_id, out)
        return out


def send_scheduled(schedule_id: str, meaning: str, examples: List[str]):
    msg = generate_scheduled_text(schedule_id, meaning, examples)
    for uid in list(user_ids):
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=msg))
        except Exception:
            pass
    print(f"[{datetime.now(timezone)}] Scheduled({schedule_id}) sent: {msg}")


# Register scheduler jobs
for schedule_id, meaning, examples, hour, minute in SCHEDULE_SLOTS:
    scheduler.add_job(
        send_scheduled,
        "cron",
        hour=hour,
        minute=minute,
        args=[schedule_id, meaning, examples],
        id=f"job_{schedule_id}",
        replace_existing=True,
    )

scheduler.start()


# =========================
# LINE webhook
# =========================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = (event.message.text or "").strip()
    user_id = event.source.user_id
    user_ids.add(user_id)

    # keep original menu for งง
    if user_text.lower() == "งง":
        reply_text = responses.get("งง", "พิมพ์ “งง” เพื่อดูคำที่ใช้ได้น้าค้าบ")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    mg, conf = route_group(user_text)
    reply_text = generate_reply(user_text, mg, conf)

    if mg != "none" and conf >= ROUTER_CONFIDENCE_THRESHOLD:
        remember_recent(recent_by_group, mg, reply_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
