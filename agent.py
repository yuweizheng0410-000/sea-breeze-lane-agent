"""
Sea Breeze Lane B&B customer service agent: database, tools and agent loop.

This file has no user interface. app.py (Gradio) and test_tool_choice.py both import it.
"""

import csv
import json
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inn.db"
DB_LOCK = threading.Lock()
DB_LOCK_WRITE = threading.Lock()  # one booking is saved at a time

INN_NAME = "Sea Breeze Lane B&B"
INN_NAME_ZH = "海風小徑民宿"
STAFF_PHONE = "03-123-4567"
STAFF_HOURS = "09:00-21:00 every day"
MAX_NIGHTS = 14
LONG_STAY_NIGHTS = 3        # 3 nights or more ...
LONG_STAY_DISCOUNT = 0.10   # ... get 10% off the room charge
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ----------------------------------------------------------------------------
# 1. Database: rebuilt from the CSV files every time the program starts
# ----------------------------------------------------------------------------

# table name -> (csv file, column definitions)
TABLES = {
    "inn_info": ("inn_info.csv",
                 "topic TEXT PRIMARY KEY, content TEXT, content_zh TEXT"),
    "rooms": ("rooms.csv",
              "room_id TEXT PRIMARY KEY, name TEXT, name_zh TEXT, room_type TEXT, "
              "room_type_zh TEXT, capacity INTEGER, max_extra_beds INTEGER, "
              "weekday_price INTEGER, weekend_price INTEGER, view TEXT, available TEXT"),
    "add_ons": ("add_ons.csv",
                "item TEXT PRIMARY KEY, item_zh TEXT, price INTEGER, unit TEXT, unit_zh TEXT"),
    "room_aliases": ("room_aliases.csv", "alias TEXT, room_id TEXT"),
    "bookings": ("bookings.csv",
                 "booking_id TEXT PRIMARY KEY, room_id TEXT, guest_name TEXT, phone TEXT, "
                 "check_in TEXT, check_out TEXT, guests INTEGER, status TEXT"),
    "holidays": ("holidays.csv", "date TEXT PRIMARY KEY, name TEXT, name_zh TEXT"),
}


def build_database():
    """Delete the old database file and build every table again from its CSV file."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    for table, (csv_name, columns) in TABLES.items():
        con.execute(f"CREATE TABLE {table} ({columns})")
        with open(BASE_DIR / csv_name, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            names = reader.fieldnames
            marks = ", ".join("?" for _ in names)
            rows = [[row[n].strip() for n in names] for row in reader]
        con.executemany(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks})", rows)
    con.commit()
    con.close()


def query(sql, params=()):
    """Run a fixed SQL statement written in this file. The model never writes SQL."""
    with DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
        con.close()
    return rows


def execute(sql, params=()):
    with DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.execute(sql, params)
        con.commit()
        con.close()


def info_topics():
    return [r["topic"] for r in query("SELECT topic FROM inn_info ORDER BY rowid")]


# ----------------------------------------------------------------------------
# 2. Helpers: dates, prices, loose room-name matching
# ----------------------------------------------------------------------------

def parse_date(text, field):
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} must be a date in the form YYYY-MM-DD, got '{text}'")


def check_dates(check_in, check_out):
    d_in = parse_date(check_in, "check_in")
    d_out = parse_date(check_out, "check_out")
    if d_in < date.today():
        raise ValueError(f"check_in {d_in} is in the past (today is {date.today()})")
    if d_out <= d_in:
        raise ValueError("check_out must be later than check_in")
    if (d_out - d_in).days > MAX_NIGHTS:
        raise ValueError(f"a stay can be at most {MAX_NIGHTS} nights")
    return d_in, d_out


def holiday_dates():
    return {r["date"]: r["name"] for r in query("SELECT date, name FROM holidays")}


def night_rate_type(night, holidays):
    """A night uses the weekend price when the NEXT day is a day off:
    Saturday, Sunday or a national holiday in holidays.csv."""
    next_day = night + timedelta(days=1)
    if next_day.weekday() == 5:
        return "weekend", "next day is Saturday"
    if next_day.weekday() == 6:
        return "weekend", "next day is Sunday"
    if next_day.isoformat() in holidays:
        return "weekend", f"next day is a holiday ({holidays[next_day.isoformat()]})"
    return "weekday", "next day is a working day"


def add_on_price(item):
    rows = query("SELECT price FROM add_ons WHERE item = ?", (item,))
    return rows[0]["price"] if rows else None


def normalize(text):
    text = str(text).lower().strip()
    text = re.sub(r"[\s\-_.,!?()（）「」、。，！？]", "", text)
    for word in ["的房間", "房間", "房型", "rooms", "room", "房"]:
        text = text.replace(word, "")
    return text


ROOM_TEXT_FIELDS = ["room_id", "name", "name_zh"]


def resolve_rooms(name):
    """Find rooms from what the customer typed. Order:
    1) exact match of room id or room name,
    2) partial match of a room name,
    3) alias table (room_aliases.csv), e.g. '有浴缸的房間' -> R302, '雙人房' -> all double rooms,
    4) partial match of a room type."""
    rooms = query("SELECT * FROM rooms ORDER BY room_id")
    key = normalize(name)
    if not key:
        return []

    exact = [r for r in rooms if any(normalize(r[f]) == key for f in ROOM_TEXT_FIELDS)]
    if exact:
        return exact

    partial = [r for r in rooms
               if any(key in normalize(r[f]) or (len(normalize(r[f])) >= 2 and normalize(r[f]) in key)
                      for f in ["name", "name_zh"])]
    if partial:
        return partial

    alias_sets = {}
    for row in query("SELECT alias, room_id FROM room_aliases"):
        alias = normalize(row["alias"])
        if alias and (alias == key or alias in key):
            alias_sets.setdefault(alias, set()).add(row["room_id"])
    if alias_sets:
        ids = set.intersection(*alias_sets.values()) or set.union(*alias_sets.values())
        return [r for r in rooms if r["room_id"] in ids]

    partial_type = [r for r in rooms
                    if any(key in normalize(r[f]) for f in ["room_type", "room_type_zh"])]
    return partial_type


def resolve_one_room(name):
    """Return (room, error). The error is a dict the tool can return as it is."""
    matches = resolve_rooms(name)
    if not matches:
        return None, {"found": False, "error": f"No room matches '{name}'."}
    if len(matches) > 1:
        return None, {"found": False, "error": f"'{name}' matches more than one room. Ask the customer which one.",
                      "matching_rooms": [room_summary(r) for r in matches]}
    return matches[0], None


def room_summary(r):
    return {
        "room_id": r["room_id"], "name": r["name"], "name_zh": r["name_zh"],
        "room_type": r["room_type"], "room_type_zh": r["room_type_zh"],
        "capacity": r["capacity"], "max_extra_beds": r["max_extra_beds"],
        "weekday_price": r["weekday_price"], "weekend_price": r["weekend_price"],
        "view": r["view"], "open_for_booking": r["available"] == "yes",
    }


def booked_room_ids(d_in, d_out):
    """Rooms that already have a confirmed booking overlapping the stay."""
    rows = query("SELECT room_id FROM bookings WHERE status = 'confirmed' "
                 "AND check_in < ? AND check_out > ?", (d_out.isoformat(), d_in.isoformat()))
    return {r["room_id"] for r in rows}


# ----------------------------------------------------------------------------
# 3. Tools. Each tool returns data (a dict), never a finished sentence.
# ----------------------------------------------------------------------------

def get_inn_info(topic):
    rows = query("SELECT topic, content, content_zh FROM inn_info WHERE topic = ?",
                 (str(topic).strip().lower(),))
    if not rows:
        return {"found": False, "error": f"No information about '{topic}'.",
                "available_topics": info_topics()}
    return {"found": True, **rows[0]}


def search_rooms(name=None, guests=None, check_in=None, check_out=None, view=None):
    rooms = resolve_rooms(name) if name else query("SELECT * FROM rooms ORDER BY room_id")
    if name and not rooms:
        return {"found": False, "error": f"No room matches '{name}'."}

    if view:
        rooms = [r for r in rooms if r["view"] == str(view).lower()]
    if guests is not None:
        guests = int(guests)
        rooms = [r for r in rooms if r["capacity"] + r["max_extra_beds"] >= guests]

    booked = set()
    dates_checked = None
    if check_in or check_out:
        if not (check_in and check_out):
            return {"found": False, "error": "Give both check_in and check_out to check free rooms."}
        d_in, d_out = check_dates(check_in, check_out)
        booked = booked_room_ids(d_in, d_out)
        dates_checked = {"check_in": d_in.isoformat(), "check_out": d_out.isoformat(),
                         "nights": (d_out - d_in).days}

    results = []
    for r in rooms:
        item = room_summary(r)
        if guests is not None:
            item["extra_beds_needed"] = max(0, guests - r["capacity"])
        if dates_checked:
            item["free_on_these_dates"] = item["open_for_booking"] and r["room_id"] not in booked
        results.append(item)

    if not results:
        return {"found": False, "error": "No room matches these conditions.", "dates": dates_checked}
    return {"found": True, "count": len(results), "dates": dates_checked, "rooms": results}


def calculate_stay_cost(room, check_in, check_out, extra_beds=0, breakfast_guests=0,
                        pickup_trips=0, guests=None):
    r, error = resolve_one_room(room)
    if error:
        return error
    if r["available"] != "yes":
        return {"found": False, "error": f"{r['name']} ({r['room_id']}) is closed and cannot be booked."}

    d_in, d_out = check_dates(check_in, check_out)
    extra_beds, breakfast_guests, pickup_trips = int(extra_beds), int(breakfast_guests), int(pickup_trips)
    if extra_beds < 0 or breakfast_guests < 0 or pickup_trips < 0:
        return {"found": False, "error": "Numbers cannot be negative."}
    if extra_beds > r["max_extra_beds"]:
        return {"found": False, "error": f"{r['name']} allows at most {r['max_extra_beds']} extra bed(s)."}
    max_guests = r["capacity"] + extra_beds
    if guests is not None and int(guests) > max_guests:
        return {"found": False,
                "error": f"{r['name']} sleeps {r['capacity']} (+{r['max_extra_beds']} extra bed). "
                         f"{guests} guests need more beds or another room."}
    if breakfast_guests > max_guests:
        return {"found": False, "error": f"Breakfast guests ({breakfast_guests}) are more than the room sleeps ({max_guests})."}

    holidays = holiday_dates()
    nights = []
    room_charge = 0
    night = d_in
    while night < d_out:
        rate_type, reason = night_rate_type(night, holidays)
        price = r["weekend_price"] if rate_type == "weekend" else r["weekday_price"]
        nights.append({"night_of": night.isoformat(), "weekday": WEEKDAY_NAMES[night.weekday()],
                       "rate": rate_type, "reason": reason, "price": price})
        room_charge += price
        night += timedelta(days=1)

    n = len(nights)
    discount = round(room_charge * LONG_STAY_DISCOUNT) if n >= LONG_STAY_NIGHTS else 0
    extra_bed_fee = add_on_price("extra_bed") * extra_beds * n
    breakfast_fee = add_on_price("breakfast") * breakfast_guests * n
    pickup_fee = add_on_price("station_pickup") * pickup_trips
    total = room_charge - discount + extra_bed_fee + breakfast_fee + pickup_fee

    return {
        "found": True,
        "room": {"room_id": r["room_id"], "name": r["name"], "name_zh": r["name_zh"],
                 "room_type": r["room_type"], "room_type_zh": r["room_type_zh"]},
        "check_in": d_in.isoformat(), "check_out": d_out.isoformat(), "nights": n,
        "nightly_prices": nights,
        "room_charge": room_charge,
        "long_stay_discount": -discount,
        "long_stay_rule": f"{int(LONG_STAY_DISCOUNT * 100)}% off the room charge for {LONG_STAY_NIGHTS}+ nights",
        "extra_bed_fee": extra_bed_fee, "extra_beds": extra_beds,
        "breakfast_fee": breakfast_fee, "breakfast_guests": breakfast_guests,
        "pickup_fee": pickup_fee, "pickup_trips": pickup_trips,
        "total": total, "currency": "TWD",
        "deposit_30_percent": round(total * 0.3),
    }


def transfer_to_human(reason):
    ticket = "HT-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    return {"transferred": True, "ticket": ticket, "reason": reason,
            "staff_phone": STAFF_PHONE, "staff_hours": STAFF_HOURS,
            "note": "A staff member will contact the customer during staff hours."}


# Each chat session keeps at most ONE booking draft in its own session dict:
# session = {"turn": number of the current customer message, "draft": {...} or None}
# The draft is kept by the program, so the model does not need to remember any draft id.


def create_booking_draft(room, check_in, check_out, guests, guest_name, phone,
                         extra_beds=0, breakfast_guests=0, pickup_trips=0, _session=None):
    session = _session if _session is not None else {"turn": 0}
    if not str(guest_name).strip() or not str(phone).strip():
        return {"created": False, "error": "Ask the customer for their name and phone number first."}
    cost = calculate_stay_cost(room, check_in, check_out, extra_beds, breakfast_guests,
                               pickup_trips, guests)
    if not cost.get("found"):
        return {"created": False, **cost}
    room_id = cost["room"]["room_id"]
    if room_id in booked_room_ids(parse_date(check_in, "check_in"), parse_date(check_out, "check_out")):
        return {"created": False, "error": f"{cost['room']['name']} is already booked on these dates."}

    data = {"room_id": room_id, "guest_name": str(guest_name).strip(), "phone": str(phone).strip(),
            "check_in": cost["check_in"], "check_out": cost["check_out"], "guests": int(guests),
            "extra_beds": int(extra_beds), "breakfast_guests": int(breakfast_guests),
            "pickup_trips": int(pickup_trips)}
    old = session.get("draft")
    if old and old["data"] == data:
        # Same booking again: keep the original draft (and the message number it was shown in).
        draft = old
    else:
        draft = {"turn": session["turn"], "data": data}
        session["draft"] = draft
    shown_before = draft["turn"] < session["turn"]
    return {"created": True, "saved": False,
            "summary": {"room": cost["room"], "guest_name": data["guest_name"], "phone": data["phone"],
                        "guests": data["guests"], "check_in": cost["check_in"],
                        "check_out": cost["check_out"], "nights": cost["nights"],
                        "extra_beds": data["extra_beds"], "breakfast_guests": data["breakfast_guests"],
                        "pickup_trips": data["pickup_trips"],
                        "total": cost["total"], "deposit_30_percent": cost["deposit_30_percent"]},
            "next_step": ("The customer has already seen this summary. If they said they confirm, "
                          "call confirm_booking now.") if shown_before else
                         ("Show this summary and ask the customer to reply 'confirm'. "
                          "Nothing is saved until confirm_booking is called after their reply.")}


def confirm_booking(_session=None):
    session = _session if _session is not None else {"turn": 0}
    draft = session.get("draft")
    if not draft:
        return {"saved": False, "error": "There is no booking draft. Collect the booking details "
                                         "and call create_booking_draft first."}
    # The program, not the prompt, makes sure the customer has seen the summary:
    # a draft cannot be confirmed in the same message that created it.
    if draft["turn"] >= session["turn"]:
        return {"saved": False,
                "error": "The customer has not seen and confirmed this summary yet. "
                         "Show the summary and wait for their reply."}
    data = draft["data"]
    with DB_LOCK_WRITE:
        d_in, d_out = parse_date(data["check_in"], "check_in"), parse_date(data["check_out"], "check_out")
        if data["room_id"] in booked_room_ids(d_in, d_out):
            session["draft"] = None
            return {"saved": False, "error": "Sorry, the room was booked by someone else in the meantime."}
        count = query("SELECT COUNT(*) AS n FROM bookings")[0]["n"]
        booking_id = f"B{count + 1:04d}"
        execute("INSERT INTO bookings (booking_id, room_id, guest_name, phone, check_in, check_out, "
                "guests, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed')",
                (booking_id, data["room_id"], data["guest_name"], data["phone"],
                 data["check_in"], data["check_out"], data["guests"]))
    session["draft"] = None
    return {"saved": True, "booking_id": booking_id, **data,
            "next_step": "Pay the 30% deposit by bank transfer within 3 days."}


# ----------------------------------------------------------------------------
# 4. Tool descriptions for the model (JSON schema)
# ----------------------------------------------------------------------------

def tool_specs():
    topics = info_topics()
    date_note = "Date in YYYY-MM-DD. Work out relative dates such as 'this Friday' from today's date."
    return [
        {"type": "function", "function": {
            "name": "get_inn_info",
            "description": "Read the inn's rules and general information: check-in/out times, address, "
                           "transportation, parking, payment, deposit, cancellation, breakfast times, pets, "
                           "smoking, Wi-Fi, quiet hours, children, luggage, nearby places. "
                           "Not for room prices or free rooms.",
            "parameters": {"type": "object", "properties": {
                "topic": {"type": "string", "enum": topics, "description": "One topic."}},
                "required": ["topic"]}}},
        {"type": "function", "function": {
            "name": "search_rooms",
            "description": "Look up rooms in the database: room types, how many guests they sleep, "
                           "weekday and weekend price per night, view, and whether a room is free on given dates. "
                           "All parameters are optional; with no parameters it lists every room.",
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "description": "Room name, room type or words the customer used, "
                                                          "e.g. 'Wave', '浪花', '海景雙人房', 'bathtub'."},
                "guests": {"type": "integer", "description": "Number of guests who need beds."},
                "check_in": {"type": "string", "description": date_note},
                "check_out": {"type": "string", "description": date_note},
                "view": {"type": "string", "enum": ["ocean", "garden", "mountain"]}},
                "required": []}}},
        {"type": "function", "function": {
            "name": "calculate_stay_cost",
            "description": "Calculate the price of a stay in code: weekday/weekend price for each night "
                           "(weekend price when the next day is Saturday, Sunday or a national holiday), "
                           "10% off the room charge for 3+ nights, extra beds, breakfast and station pick-up. "
                           "Use this for ANY question about how much a stay costs. Never do the maths yourself.",
            "parameters": {"type": "object", "properties": {
                "room": {"type": "string", "description": "One room name or room id, e.g. 'Wave' or 'R201'."},
                "check_in": {"type": "string", "description": date_note},
                "check_out": {"type": "string", "description": date_note},
                "extra_beds": {"type": "integer", "description": "Extra beds, default 0."},
                "breakfast_guests": {"type": "integer", "description": "Guests who want breakfast, default 0."},
                "pickup_trips": {"type": "integer", "description": "Station pick-up trips, default 0."},
                "guests": {"type": "integer", "description": "Total guests, if known."}},
                "required": ["room", "check_in", "check_out"]}}},
        {"type": "function", "function": {
            "name": "create_booking_draft",
            "description": "Step 1 of booking. Check the room and dates and make a booking summary. "
                           "This does NOT save the booking. Ask for the guest's name and phone first.",
            "parameters": {"type": "object", "properties": {
                "room": {"type": "string"}, "check_in": {"type": "string", "description": date_note},
                "check_out": {"type": "string", "description": date_note},
                "guests": {"type": "integer"}, "guest_name": {"type": "string"},
                "phone": {"type": "string"}, "extra_beds": {"type": "integer"},
                "breakfast_guests": {"type": "integer"}, "pickup_trips": {"type": "integer"}},
                "required": ["room", "check_in", "check_out", "guests", "guest_name", "phone"]}}},
        {"type": "function", "function": {
            "name": "confirm_booking",
            "description": "Step 2 of booking. Save the booking draft that the customer saw in an earlier "
                           "message. Call it when the customer replies that they confirm (e.g. '確認', 'yes', "
                           "'confirm'). It takes no arguments; the program remembers the draft.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {
            "name": "transfer_to_human",
            "description": "Hand the customer to a staff member: complaints, refunds or changes to an existing "
                           "booking, asking for a manager, or any question about this inn that the other tools cannot answer, "
                           "such as a service or facility that is not in the get_inn_info topics "
                           "(e.g. spa, laundry, swimming pool). Never just say 'I don't know' without calling this tool.",
            "parameters": {"type": "object", "properties": {
                "reason": {"type": "string", "description": "Short reason for the transfer."}},
                "required": ["reason"]}}},
    ]


TOOLS = {
    "get_inn_info": get_inn_info,
    "search_rooms": search_rooms,
    "calculate_stay_cost": calculate_stay_cost,
    "create_booking_draft": create_booking_draft,
    "confirm_booking": confirm_booking,
    "transfer_to_human": transfer_to_human,
}
TOOLS_WITH_SESSION = {"create_booking_draft", "confirm_booking"}


# ----------------------------------------------------------------------------
# 5. System prompt: a role plus four kinds of rules
# ----------------------------------------------------------------------------

def reply_language(text):
    """The program, not the model, decides the reply language (bonus: bilingual)."""
    return "Traditional Chinese (繁體中文)" if re.search(r"[一-鿿]", text or "") else "English"


def system_prompt(language):
    today = date.today()
    return f"""You are the online customer service assistant of {INN_NAME} ({INN_NAME_ZH}), a small B&B in Hualien, Taiwan.
Today is {today.isoformat()} ({WEEKDAY_NAMES[today.weekday()]}).

Grounding rules:
- Answer only from tool results. Never invent prices, rooms, dates, rules or phone numbers.
- If a tool says found=false or returns an error, say you do not have that information and offer to transfer the customer to staff.
- Never calculate prices yourself; always use calculate_stay_cost and repeat its numbers.

Scope rules:
- Only talk about this inn: rooms, prices, bookings, rules and travel to the inn.
- Questions about this inn's services or facilities ARE in scope, even when the data does not mention them.
- Politely decline anything that is not about this inn (homework, coding, general knowledge, chat, other hotels) and bring the talk back to the inn. Do not call a tool for these.

Routing rules:
- Rules and general information (check-in, parking, payment, cancellation, pets, breakfast times...) -> get_inn_info.
- Room types, guests per room, price per night, free rooms on dates -> search_rooms.
- "How much is a stay" -> calculate_stay_cost.
- Booking -> ask for name, phone, dates and guests, call create_booking_draft, show the summary and ask the customer to confirm.
- When the customer replies that they confirm the booking summary you showed, call confirm_booking (no arguments). Do not make a new draft.
- Complaints, refunds, changing an existing booking, asking for a manager -> transfer_to_human.
- A question about this inn that no get_inn_info topic covers (for example a service or facility we may not have) -> say you do not have that information AND call transfer_to_human in the same reply.
- Turn relative dates ("this Friday", "next weekend") into YYYY-MM-DD from today's date. If the dates or number of guests are unclear, ask the customer.

Language and format rules:
- Reply in {language}. Use the room names in that language.
- Keep answers short: three sentences or fewer, unless you are showing a price breakdown or booking summary.
- Write prices as NT$ with thousands separators."""


GREETING = (f"您好，歡迎來到{INN_NAME_ZH}！我可以回答房型、房價、空房、訂房與住宿規定等問題。\n\n"
            f"Hello and welcome to {INN_NAME}! Ask me about rooms, prices, free dates, bookings or house rules.")


# ----------------------------------------------------------------------------
# 6. Agent loop: safe (max_steps, only our tools) and visible (tool trace)
# ----------------------------------------------------------------------------

def make_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(BASE_DIR / ".env")
    client = OpenAI(base_url=os.getenv("LLM_API_URL"), api_key=os.getenv("API_KEY") or "none")
    return client, os.getenv("MODEL_NAME")


def run_tool(name, raw_args, session):
    if name not in TOOLS:
        return {"error": f"Unknown tool '{name}'. Only these tools exist: {', '.join(TOOLS)}."}, {}
    try:
        args = json.loads(raw_args) if raw_args else {}
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"Bad arguments: {e}"}, {}
    args = {k: v for k, v in args.items() if v is not None and not str(k).startswith("_")}
    try:
        call_args = dict(args, _session=session) if name in TOOLS_WITH_SESSION else args
        return TOOLS[name](**call_args), args
    except (TypeError, ValueError) as e:
        return {"error": str(e)}, args


def new_session():
    return {"turn": 0, "draft": None}


def run_agent(client, model, history, user_message, session, max_steps=6):
    """history: earlier messages [{'role': 'user'|'assistant', 'content': str}].
    session: dict from new_session(), kept for one chat; its turn number goes up by one here.
    Returns (answer, trace) where trace lists every tool call."""
    session["turn"] += 1
    language = reply_language(user_message)
    messages = [{"role": "system", "content": system_prompt(language)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history
                 if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    messages.append({"role": "user", "content": user_message})

    specs = tool_specs()
    trace = []
    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(model=model, messages=messages, tools=specs)
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []
        if not tool_calls:
            return (msg.content or "").strip(), trace

        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name,
                                                      "arguments": c.function.arguments}}
                                        for c in tool_calls]})
        for call in tool_calls:
            result, args = run_tool(call.function.name, call.function.arguments, session)
            trace.append({"step": step, "tool": call.function.name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, ensure_ascii=False)})

    fallback = ("抱歉，這個問題我目前無法處理，已建議您聯絡真人客服。" if language.startswith("Traditional")
                else "Sorry, I could not finish this request. Please contact our staff.")
    trace.append({"step": max_steps, "tool": "(stopped)", "arguments": {},
                  "result": {"error": f"Reached max_steps={max_steps}."}})
    return f"{fallback} ({STAFF_PHONE})", trace
