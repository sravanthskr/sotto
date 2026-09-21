import os
from groq import Groq
from dotenv import load_dotenv
from config import SYSTEM_PROMPT, MODEL_NAME

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Define the tool for Groq's Native Function Calling
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open an application on the user's computer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the application to open, e.g., Chrome, Spotify, Notepad"
                    }
                },
                "required": ["app_name"]
            }
        }
    }
]


def summarize_messages(messages_to_summarize):
    conversation_text = str(messages_to_summarize)
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system",
             "content": "Summarize the key facts, actions taken, and user preferences from the conversation below. Keep it under 50 words. Only output the summary."},
            {"role": "user", "content": conversation_text}
        ],
        model=MODEL_NAME,
    )
    return chat_completion.choices[0].message.content


def ask_ai(conversation_summary, chat_history):
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_summary:
        full_messages.append({"role": "system", "content": f"Previous conversation summary: {conversation_summary}"})
    full_messages.extend(chat_history)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=full_messages,
        tools=TOOLS_SCHEMA,
        tool_choice="auto"  # The AI decides when to use the tool
    )

    # Return the whole message object, not just the text
    return response.choices[0].message