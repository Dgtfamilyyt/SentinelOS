from ai.engine import AIEngine
from core.banner import show_banner
from core.logger import logger

def main():
    show_banner()

    logger.info("Sentinel OS Started")

    ai = AIEngine()

    while True:
        prompt = input("\nYou: ")

        logger.info(f"User: {prompt}")

        if prompt.lower() in ["exit", "quit"]:
            logger.info("Sentinel Shutdown")
            break

        if prompt.lower() == "/clear":
            ai.conversation.clear()
            logger.info("Conversation Cleared")
            print("🧹 Conversation cleared.")
            continue

        # This line is VERY IMPORTANT
        answer = ai.ask(prompt)

        print(f"\nSentinel:\n{answer}")

    print("👋 Goodbye, DGT!")

if __name__ == "__main__":
    main()