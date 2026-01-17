import os
import re
import json
import random
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import pytz
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from apscheduler.schedulers.background import BackgroundScheduler

from openai import OpenAI


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

# OpenAI
# Official SDK reads OPENAI_API_KEY automatically, but we still validate for clearer error
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY in environment variables")

client = OpenAI()

ROUTER_MODEL = os.getenv("OPENAI_ROUTER_MODEL", "gpt-5-mini")
WRITER_MODEL = os.getenv("OPENAI_WRITER_MODEL", "gpt-5-mini")

# Behavior tuning
ROUTER_CONFIDENCE_THRESHOLD = float(os.getenv("ROUTER_CONFIDENCE_THRESHOLD", "0.65"))
MAX_RECENT_PER_GROUP = int(os.getenv("MAX_RECENT_PER_GROUP", "10"))

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
    # Shuffle inside groups so references aren’t always same order
    for g in groups:
        random.shuffle(groups[g])
    return groups

GROUPS = build_groups(responses)
ALLOWED_GROUPS = sorted(GROUPS.keys())  # router menu


# =========================
# OpenAI: Router (choose group)
# =========================
def _safe_json_load(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        # Try to extract a JSON object if model added extra text
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

def route_group(user_text: str) -> Tuple[str, float]:
    """
    Returns (match_group, confidence). match_group in ALLOWED_GROUPS or "none".
    """
    router_instructions = (
        "You are a strict classifier for a LINE chat bot.\n"
        "Return ONLY valid JSON with keys: match_group (string) and confidence (number 0..1).\n"
        f"Allowed match_group values: {ALLOWED_GROUPS + ['none']}\n"
        "Pick the closest group by meaning, even if the user uses slang/typos/elongations.\n"
        "If nothing fits, return match_group='none'.\n"
        "No extra text."
    )

    r = client.responses.create(
        model=ROUTER_MODEL,
        input=user_text,
        instructions=router_instructions,
    )

    # SDK returns a structured response; simplest reliable extraction is output_text
    raw = getattr(r, "output_text", "") or ""
    data = _safe_json_load(raw)

    if not data:
        return ("none", 0.0)

    mg = str(data.get("match_group", "none"))
    conf = float(data.get("confidence", 0.0) or 0.0)

    if mg not in ALLOWED_GROUPS and mg != "none":
        return ("none", 0.0)

    conf = max(0.0, min(1.0, conf))
    return (mg, conf)


# =========================
# OpenAI: Writer (always new)
# =========================
PERSONA = (
    "สไตล์การคุย: ไทย น่ารัก กวนๆ หยอดๆ ขี้เล่น อบอุ่นบ้าง แซวบ้าง\n"
    "ชอบใช้คำลากเสียง เช่น งงง น้าาา หื้มมม และคำติดปากแบบ ค้าบ, อ้วนๆ, จุ๊บมั๊ว\n"
    "ไม่ต้องพูดว่าตัวเองเป็น AI และไม่ต้องอธิบายระบบ\n"
    "ถ้าผู้ใช้ถามคำถามจริงจัง ให้ตอบให้เป็นประโยชน์ แต่ยังคุมโทนให้น่ารักได้\n"
)

def remember_recent(store: Dict[str, List[str]], key: str, text: str):
    store.setdefault(key, []).append(text)
    if len(store[key]) > MAX_RECENT_PER_GROUP:
        store[key] = store[key][-MAX_RECENT_PER_GROUP:]

def generate_reply(user_text: str, match_group: str, confidence: float) -> str:
    """
    Flexible length:
    - Short playful by default
    - If user asks a real question, answer normally (still in style)
    Always brand-new, never copy references.
    """
    recent = recent_by_group.get(match_group, []) if match_group != "none" else []
    refs = GROUPS.get(match_group, []) if match_group != "none" else []

    # Keep refs short so prompt isn’t huge
    ref_snippet = "\n".join([f"- {t}" for t in refs[:6]]) if refs else ""

    avoid_snippet = "\n".join([f"- {t}" for t in recent[-6:]]) if recent else ""

    writer_instructions = (
        PERSONA +
        "\nข้อกำหนดสำคัญ:\n"
        "- ต้องแต่งประโยคใหม่ทุกครั้ง ห้ามคัดลอกประโยคเดิมตรงๆ\n"
        "- ถ้าเข้ากลุ่มที่จับคู่ได้ ให้ตอบ “ความหมายใกล้เคียง” กับตัวอย่าง แต่เปลี่ยนคำทั้งหมด\n"
        "- ถ้าผู้ใช้ถามคำถาม ให้ตอบคำถามนั้นจริงๆ ไม่หลบคำถาม\n"
        "- ความยาวยืดหยุ่นตามข้อความผู้ใช้ (สั้นได้ ยาวได้ถ้าจำเป็น)\n"
    )

    context = ""
    if match_group != "none" and confidence >= ROUTER_CONFIDENCE_THRESHOLD and ref_snippet:
        context = (
            f"\nกลุ่มที่จับคู่ได้: {match_group} (confidence={confidence:.2f})\n"
            "ตัวอย่างสไตล์/ความหมาย (ห้ามคัดลอกคำตรงๆ):\n"
            f"{ref_snippet}\n"
        )
    else:
        context = "\nจับคู่กลุ่มไม่ได้หรือความมั่นใจต่ำ: ตอบแบบคุยอิสระตามสไตล์\n"

    if avoid_snippet:
        context += (
            "\nประโยคล่าสุดที่เคยตอบ (พยายามอย่าให้ซ้ำโครงมาก):\n"
            f"{avoid_snippet}\n"
        )

    prompt_input = (
        f"{context}\n"
        f"ข้อความผู้ใช้: {user_text}\n"
        "ตอบกลับ:"
    )

    r = client.responses.create(
        model=WRITER_MODEL,
        input=prompt_input,
        instructions=writer_instructions,
    )

    out = (getattr(r, "output_text", "") or "").strip()
    if not out:
        out = "หื้มม พิมพ์มาใหม่ได้มะ เค้าอ่านไม่ทันง้าบบ 😳"
    return out


# =========================
# Scheduled messages (AI rewrite)
# =========================
SCHEDULE_SLOTS = [
    # (schedule_id, base_meaning, examples, hour, minute)
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

    instructions = (
        PERSONA +
        "\nงานของคุณ:\n"
        "- สร้างข้อความ 1 ข้อความสำหรับส่งตามเวลา (scheduled)\n"
        "- ต้องสื่อความหมายตามที่กำหนด\n"
        "- ใช้โทน/สไตล์คล้ายตัวอย่าง แต่ห้ามคัดลอกตรงๆ\n"
        "- ความยาวสั้นถึงกลาง (อย่ายาวเป็นพารากราฟ)\n"
        "- แต่งใหม่ทุกครั้ง\n"
    )

    ctx = (
        f"หัวข้อ/ความหมายที่ต้องการ: {meaning}\n"
        "ตัวอย่างสไตล์ (ห้ามคัดลอกตรงๆ):\n"
        f"{ex}\n"
    )
    if avoid:
        ctx += (
            "\nข้อความล่าสุดที่เคยส่ง (พยายามอย่าซ้ำ):\n"
            f"{avoid}\n"
        )

    r = client.responses.create(
        model=WRITER_MODEL,
        input=ctx + "\nสร้างข้อความใหม่ 1 ข้อความ:",
        instructions=instructions,
    )

    out = (getattr(r, "output_text", "") or "").strip()
    if not out:
        out = examples[0]
    remember_recent(recent_schedule, schedule_id, out)
    return out

def send_scheduled(schedule_id: str, meaning: str, examples: List[str]):
    msg = generate_scheduled_text(schedule_id, meaning, examples)
    for uid in list(user_ids):
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=msg))
        except Exception:
            # If push fails (blocked user etc.), you might want to remove uid in a real DB
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

    # AI route → write
    mg, conf = route_group(user_text)

    # Special: if user types "งง" you might want to keep your original menu response
    # If you want AI to still rewrite it, remove this block.
    if user_text.strip().lower() == "งง":
        reply_text = responses.get("งง")
    else:
        reply_text = generate_reply(user_text, mg, conf)

    # remember recent by matched group (only if it was confident enough)
    if mg != "none" and conf >= ROUTER_CONFIDENCE_THRESHOLD:
        remember_recent(recent_by_group, mg, reply_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
