# Tool-choice test

Model: `Furen-large`  
Accuracy: **13/14 = 93%**

| # | Category | Question | Accepted | Tools called | OK | Answer |
|---|---|---|---|---|---|---|
| 1 | in data | 入住時間是幾點？ | get_inn_info | get_inn_info | ✅ | 入住時間為 15:00 至 21:00。若需於 21:00 後抵達，請事先來電安排。退房時間為 11:00 前，亦可加購延遲至 13:00。 |
| 2 | in data | Is there free parking? | get_inn_info | get_inn_info | ✅ | Yes, the inn offers 12 free parking spaces on a first‑come, first‑served basis. If they’re full, there’s a public paid car park about a three‑minute walk away on Haifeng Road. |
| 3 | in data | 可以刷卡嗎？ | get_inn_info | get_inn_info | ✅ | 可以刷卡的！我們接受 Visa、Mastercard、JCB 信用卡，也可使用 LINE Pay。若需要其他付款方式，也可使用現金。 |
| 4 | in data | 你們有幾人房？最多可以住幾個人？ | search_rooms | search_rooms | ✅ | 我們提供1人房、2人房、3人房、4人房和6人房等多種房型。其中容納人數最多的是「太平洋」家庭套房，可住6位房客。其他房型則依room capacity分別為1～4人。 |
| 5 | in data | 2026-11-06 到 2026-11-08 還有四人房嗎？ | search_rooms | search_rooms | ✅ | 有，以下四人房在 2026-11-06 至 2026-11-08 期間可訂：海景家庭套房（Pacific）與山景四人房（Firefly）。珊瑚房（Coral）雖為四人房但目前已滿。 |
| 6 | in data | Do you have a room with a bathtub? | search_rooms | search_rooms | ✅ | Yes, we have the Starfish room—a balcony double room with a bathtub and ocean view. It sleeps up to 2 guests (with space for one extra bed). Would you like to check availability or get a price for specific dates? |
| 7 | calculation | 浪花房 2026-11-13 住到 2026-11-16，兩個人含早餐總共多少錢？ | calculate_stay_cost | calculate_stay_cost | ✅ | 浪花房在 2026‑11‑13 入住至 2026‑11‑16（共 3 晚），兩人含早餐的總費用為 **NT$11,580**（含 10% 三晚以上住宿折扣與早餐費）。如需預訂，請提供您的姓名與聯絡電話，我可為您建立預訂草稿。 |
| 8 | calculation | How much is the Family Suite from 2026-12-24 to 2026-12-26? | calculate_stay_cost | calculate_stay_cost | ✅ | The Family Suite (Pacific) for 2 nights from 2026‑12‑24 to 2026‑12‑26 costs NT$16,400. This includes the nightly rates (both nights are charged at the weekend rate due to nearby holidays) and no additional fees. A 30 % deposit (NT$4,920) would be required to confirm the booking. |
| 9 | calculation | 貝殼房加一張床，2026-11-20 住一晚多少錢？ | calculate_stay_cost | calculate_stay_cost | ✅ | 貝殼房加一張床，2026-11-20 住一晚的總費用為 **NT$3,600**（含房費 NT$3,000、加床費 NT$600）。若需進一步預訂或有其他問題，請告訴我。 |
| 10 | not in data | 你們有提供按摩服務嗎？ | get_inn_info / transfer_to_human | none | ❌ | 我目前沒有關於按摩服務的資訊。若您想了解民宿的房型、價格、訂房或住宿相關規定，我很樂意為您提供協助。您想詢問哪一方面的資訊呢？ |
| 11 | not in data | 我要找經理，我對上次的住宿很不滿意。 | transfer_to_human | transfer_to_human | ✅ | 我已將您的請求轉交給經理處理。您的工單編號是 HT-20261026-180337，專線電話為 03-123-4567，服務時間為每日 09:00‑21:00，工作人員會在此時段內與您聯繫。如有其他關於民宿的問題，我很樂意協助。 |
| 12 | not in data | 可以幫我把已經訂好的房間改到下個月嗎？ | transfer_to_human | transfer_to_human | ✅ | 已將您的「變更已訂房間」請求轉交給民宿工作人員處理。   您的工單號碼為 **HT-20261026-180345**，工作人員將於服務時間（09:00‑21:00）透過電話 **03-123-4567** 與您聯繫。如有其他問題，請隨時告訴我。 |
| 13 | out of scope | 幫我寫一段 Python 程式。 | none | none | ✅ | 抱歉，我只能協助海風小徑民宿相關的問題，如房型、價格、預訂或規則。您是否需要查詢民宿的房間資訊或其他住宿相關問題？ |
| 14 | out of scope | What is the capital of France? | none | none | ✅ | I’m sorry, I can only assist with questions about Sea Breeze Lane B&B—such as rooms, prices, bookings, or getting here. How can I help you with your stay? |
