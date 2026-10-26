# Sea Breeze Lane B&B Helper: Answers Questions About Rooms, Prices, Free Dates and Bookings

An AI customer service agent for **Sea Breeze Lane B&B (海風小徑民宿)**, a small fictional B&B in Hualien, Taiwan.
Guests can ask about house rules, find a free room, get the exact price of a stay and make a booking,
in Traditional Chinese or English. Every answer comes from tools that read a SQLite database or calculate in code.

> Course homework: Unit G, My AI Customer Service Agent, with a Database and Tools
> Student: [F115118136] [鄭淯蔚]

![Main screen of my agent, with the tool trace](images/screenshot-main.png)

## Who It Serves and When They Use It

- **Who uses it:** travellers planning a trip to Hualien, both Taiwanese and foreign guests.
- **When they use it:** while planning a trip, often in the evening, when nobody can answer the phone.
- **What problem it solves:** guests ask the same questions about parking, check-in and prices every day, and
  the price of a stay depends on weekends, national holidays, long-stay discounts and add-ons, which is easy to get wrong by hand.

## What It Can Do

| Function | Example question | Tool it uses |
|---|---|---|
| Tell house rules: check-in, parking, payment, cancellation, pets... | "停車位夠嗎？" | `get_inn_info` |
| Find rooms and check free dates | "11 月 6 日到 8 日有四人房嗎？" | `search_rooms` |
| Work out the price of a stay | "浪花房住三晚含早餐多少錢？" | `calculate_stay_cost` |
| Make a booking (summary first, saved only after the guest confirms) | "我要訂房" → "確認" | `create_booking_draft`, `confirm_booking` |
| Hand over to a person | "我要客訴。" | `transfer_to_human` |

## How It Works

Every question goes to the agent first. The agent chooses a tool, the tool reads the database
or calculates in code, and the agent answers only from what the tool returns.

- **Model:** Furen-large (NKUST AI Hub, OpenAI-compatible API)
- **Chat screen:** Gradio, with a "Tools used" panel that shows each tool call, its arguments and its result
- **Database (SQLite):** built from the CSV files every time the program starts.

  | Table | CSV file | What it holds | Rows |
  |---|---|---|---|
  | `inn_info` | `inn_info.csv` | topics such as check-in, parking, payment, cancellation (English and Chinese) | 14 |
  | `rooms` | `rooms.csv` | rooms, room type, guests, extra beds, weekday and weekend price, view, open or closed | 16 |
  | `add_ons` | `add_ons.csv` | prices of breakfast, extra bed, station pick-up and more | 6 |
  | `room_aliases` | `room_aliases.csv` | other words guests use for rooms, e.g. "浴缸" → Starfish | 94 |
  | `bookings` | `bookings.csv` | existing bookings, used to check free dates; new bookings are added here | 8 |
  | `holidays` | `holidays.csv` | Taiwan national holidays (days off on weekdays), 2026–2027 | 22 |

- **Tools:**

  | Tool | What it does |
  |---|---|
  | `get_inn_info(topic)` | reads one topic from `inn_info`; returns `found: false` and the list of topics if it does not exist |
  | `search_rooms(name, guests, check_in, check_out, view)` | finds rooms with loose name matching and checks `bookings` for free dates |
  | `calculate_stay_cost(room, check_in, check_out, extra_beds, breakfast_guests, pickup_trips, guests)` | prices each night in code, adds discounts and add-ons |
  | `create_booking_draft(...)` | checks the booking and returns a summary; nothing is saved |
  | `confirm_booking(draft_id)` | saves the draft to `bookings`, only in a later message than the draft |
  | `transfer_to_human(reason)` | gives a ticket number and the staff phone number |

### How the price is calculated

1. Each night uses the **weekend price when the next day is a day off** (Saturday, Sunday or a national holiday in `holidays.csv`),
   otherwise the weekday price. So Friday and Saturday nights, and the night before a holiday, use the weekend price.
2. A stay of **3 nights or more gets 10% off** the room charge.
3. Extra beds: NT$600 × beds × nights. Breakfast: NT$250 × guests × nights. Station pick-up: NT$400 per trip.
   All add-on prices are read from `add_ons.csv`.

### Safety

- The agent loop calls the model at most `max_steps` (6) times per question.
- Only the six tools above can run; any other tool name is refused.
- The model only fills in tool arguments; all SQL is written in `agent.py`.
- A booking draft **cannot be confirmed in the same message that created it**. This is checked in code, so the guest always sees the summary before anything is written to the database.
- The reply language (Traditional Chinese or English) is chosen by the program from the guest's message.

## Sample Conversations

![A question that uses the calculation tool](images/screenshot-1.png)

![A question the data does not cover](images/screenshot-2.png)

## Project Files

```text
sea-breeze-lane-agent/
├── app.py               # the Gradio chat screen with the "Tools used" panel
├── agent.py             # database, tools, system prompt and agent loop
├── test_tool_choice.py  # tool-choice test (14 questions), writes test_results.md
├── inn_info.csv         # the information table
├── rooms.csv            # the records table
├── add_ons.csv          # add-on prices used by the calculation tool
├── room_aliases.csv     # other names for rooms (loose name matching)
├── bookings.csv         # existing bookings
├── holidays.csv         # national holidays used for weekend prices
├── requirements.txt     # the Python packages to install
├── .env.example         # a sample settings file (no real key)
├── .gitignore           # files git must not upload: .env and *.db
├── images/              # screenshots for this README
└── README.md            # this file
```

## How to Install and Run It

1. Download the project:

   ```bash
   git clone https://github.com/[your-account]/[your-repo].git
   cd [your-repo]
   ```

2. Install the packages (Python 3.10 or newer):

   ```bash
   pip install -r requirements.txt
   ```

3. Make your settings file. Copy `.env.example` to `.env`, then put your own API key after `API_KEY=`.
   The model must support tool calling.

   ```bash
   copy .env.example .env      # Windows
   cp .env.example .env        # macOS or Linux
   ```

4. Start the agent. It builds the database from the CSV files, then opens the chat page:

   ```bash
   python app.py
   ```

5. Open the link shown in the console, usually <http://127.0.0.1:7860>.

6. (Optional) Run the tool-choice test:

   ```bash
   python test_tool_choice.py
   ```

## Notes

- All names, the address, phone numbers, prices and bookings in the data are **made up**.
  The holiday dates follow the 2026 and 2027 government office calendars published by the
  Directorate-General of Personnel Administration, Taiwan.
- The `.env` file holds the API key. It is **not** in this repository. Make your own from `.env.example`.
- New bookings are saved in `inn.db` while the program runs. The database is rebuilt from the CSV files at every start, so they are cleared when the program restarts.
- Dates in the past are refused, so the sample dates in the test file may need to be moved forward later.
