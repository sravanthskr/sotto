import json
from ai_engine import ask_ai, summarize_messages
from tools import open_application, build_start_menu_cache


def main():
    print("Assistant is starting up...")
    build_start_menu_cache()
    print("Assistant is running. Type 'exit' to quit.")

    chat_history = []
    conversation_summary = ""

    while True:
        user_text = input("You: ")
        if user_text.lower() == 'exit':
            break

        chat_history.append({"role": "user", "content": user_text})

        # Get AI message object
        message = ask_ai(conversation_summary, chat_history)

        # Check if AI decided to use a native tool
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "open_application":
                    # Extract the arguments safely
                    args = json.loads(tool_call.function.arguments)
                    app_name = args.get("app_name")

                    print(f"[System: AI wants to open {app_name}]")

                    # Execute the tool
                    result = open_application(app_name)
                    print("System:", result)

                    # Add AI's tool call to history
                    chat_history.append(message)
                    # Add the tool result to history so AI knows what happened
                    chat_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": "open_application",
                        "content": result
                    })

                    # Ask AI to respond based on the result
                    final_message = ask_ai(conversation_summary, chat_history)
                    print("AI:", final_message.content)
                    chat_history.append({"role": "assistant", "content": final_message.content})
        else:
            # Normal conversation
            print("AI:", message.content)
            chat_history.append({"role": "assistant", "content": message.content})

        # Memory compression
        if len(chat_history) > 6:
            old_msgs = chat_history[:4]
            new_summary = summarize_messages(old_msgs)
            conversation_summary += " " + new_summary
            chat_history = chat_history[-2:]
            print("\n[System: Memory compressed to save tokens.]\n")


if __name__ == "__main__":
    main()