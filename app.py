"""
Sea Breeze Lane B&B customer service agent: Gradio chat screen.

Run:  python app.py
The database is rebuilt from the CSV files every time the program starts.
"""

import json

import gradio as gr

import agent

MAX_STEPS = 6
EXAMPLES = [
    "入住和退房時間是幾點？",
    "停車位夠嗎？車位滿了怎麼辦？",
    "11 月 6 日到 11 月 8 日有四人房嗎？",
    "浪花房 11 月 13 日住到 11 月 16 日，兩個人含早餐多少錢？",
    "Do you have a room with a bathtub?",
    "我要訂房",
    "可以帶貓嗎？",
    "我上次入住的房間很髒，我要客訴。",
    "幫我寫一首關於大海的詩。",
]

agent.build_database()
CLIENT, MODEL = agent.make_client()


def show_trace(trace):
    """Markdown for the 'Tools used' panel: tool name, arguments and result of every call."""
    if not trace:
        return "_No tool was called for the last question._"
    parts = []
    for i, t in enumerate(trace, 1):
        result = json.dumps(t["result"], ensure_ascii=False, indent=2)
        if len(result) > 2500:
            result = result[:2500] + "\n... (cut)"
        parts.append(f"**{i}. `{t['tool']}`** (step {t['step']})\n\n"
                     f"Arguments:\n```json\n{json.dumps(t['arguments'], ensure_ascii=False)}\n```\n"
                     f"Result:\n```json\n{result}\n```")
    return "\n\n---\n\n".join(parts)


def respond(user_message, history, session):
    user_message = (user_message or "").strip()
    if not user_message:
        return "", history, history, gr.update(), session
    try:
        answer, trace = agent.run_agent(CLIENT, MODEL, history, user_message, session, MAX_STEPS)
    except Exception as e:  # API errors such as a wrong key or 429 too many requests
        answer, trace = f"⚠️ API error: {e}", []
    history = history + [{"role": "user", "content": user_message},
                         {"role": "assistant", "content": answer or "(empty answer)"}]
    return "", history, history, show_trace(trace), session


def clear():
    start = [{"role": "assistant", "content": agent.GREETING}]
    return start, start, "_No tool has been called yet._", agent.new_session()


def make_chatbot(start):
    try:  # Gradio 5 needs type="messages"; Gradio 6 removed the parameter
        return gr.Chatbot(value=start, type="messages", height=560, label="Chat")
    except TypeError:
        return gr.Chatbot(value=start, height=560, label="Chat")


with gr.Blocks(title=f"{agent.INN_NAME} Customer Service") as demo:
    gr.Markdown(f"# 🌊 {agent.INN_NAME_ZH} {agent.INN_NAME}\n"
                f"AI customer service · Model: `{MODEL}` · All data is fictional.")
    start = [{"role": "assistant", "content": agent.GREETING}]
    history_state = gr.State(start)
    session_state = gr.State(agent.new_session())

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = make_chatbot(start)
            with gr.Row():
                box = gr.Textbox(placeholder="請輸入問題 / Type your question", show_label=False, scale=5)
                send = gr.Button("Send", variant="primary", scale=1)
            gr.Examples(EXAMPLES, inputs=box, label="Example questions")
            reset = gr.Button("New conversation")
        with gr.Column(scale=2):
            gr.Markdown("### 🔧 Tools used")
            trace_box = gr.Markdown("_No tool has been called yet._")

    outputs = [box, chatbot, history_state, trace_box, session_state]
    send.click(respond, [box, history_state, session_state], outputs)
    box.submit(respond, [box, history_state, session_state], outputs)
    reset.click(clear, None, [chatbot, history_state, trace_box, session_state])


if __name__ == "__main__":
    demo.launch()
