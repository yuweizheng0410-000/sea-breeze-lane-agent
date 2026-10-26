"""
Tool-choice test (like Step 9 of the Unit G-3 notebook).

Each question lists the tools we accept as the FIRST choice. "none" means the agent
should answer without any tool (for example, a question that is not about the inn).
Run:  python test_tool_choice.py
The results are printed and saved to test_results.md.
"""

import sys
import time

import agent

SLEEP_SECONDS = 5  # free API plans allow about 15 calls a minute; each question needs 2 or more

TESTS = [
    # (category, question, accepted first tools)
    ("in data", "入住時間是幾點？", {"get_inn_info"}),
    ("in data", "Is there free parking?", {"get_inn_info"}),
    ("in data", "可以刷卡嗎？", {"get_inn_info"}),
    ("in data", "你們有幾人房？最多可以住幾個人？", {"search_rooms"}),
    ("in data", "2026-11-06 到 2026-11-08 還有四人房嗎？", {"search_rooms"}),
    ("in data", "Do you have a room with a bathtub?", {"search_rooms"}),
    ("calculation", "浪花房 2026-11-13 住到 2026-11-16，兩個人含早餐總共多少錢？", {"calculate_stay_cost"}),
    ("calculation", "How much is the Family Suite from 2026-12-24 to 2026-12-26?", {"calculate_stay_cost"}),
    ("calculation", "貝殼房加一張床，2026-11-20 住一晚多少錢？", {"calculate_stay_cost"}),
    ("not in data", "你們有提供按摩服務嗎？", {"transfer_to_human", "get_inn_info"}),
    ("not in data", "我要找經理，我對上次的住宿很不滿意。", {"transfer_to_human"}),
    ("not in data", "可以幫我把已經訂好的房間改到下個月嗎？", {"transfer_to_human"}),
    ("out of scope", "幫我寫一段 Python 程式。", {"none"}),
    ("out of scope", "What is the capital of France?", {"none"}),
]


def main():
    agent.build_database()
    client, model = agent.make_client()
    rows, correct = [], 0
    for i, (category, question, accepted) in enumerate(TESTS, 1):
        try:
            answer, trace = agent.run_agent(client, model, [], question, agent.new_session())
        except Exception as e:
            answer, trace = f"API error: {e}", []
        first = trace[0]["tool"] if trace else "none"
        ok = first in accepted
        correct += ok
        all_tools = ", ".join(t["tool"] for t in trace) or "none"
        rows.append((i, category, question, " / ".join(sorted(accepted)), all_tools, "✅" if ok else "❌",
                     answer.replace("\n", " ")))
        print(f"{i:2d}. {'OK ' if ok else 'BAD'} [{category}] {question}\n    tools: {all_tools}\n    answer: {answer}\n")
        time.sleep(SLEEP_SECONDS)

    score = f"{correct}/{len(TESTS)} = {correct / len(TESTS):.0%}"
    print("Tool-choice accuracy:", score)
    with open("test_results.md", "w", encoding="utf-8") as f:
        f.write(f"# Tool-choice test\n\nModel: `{model}`  \nAccuracy: **{score}**\n\n")
        f.write("| # | Category | Question | Accepted | Tools called | OK | Answer |\n|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |\n")
    return 0 if correct == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
