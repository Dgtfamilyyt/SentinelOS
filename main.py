from core.banner import show_banner
from core.command_center import CommandCenter
from core.logger import logger


def main():
    show_banner()

    logger.info("Sentinel OS Started")

    center = CommandCenter()

    while True:

        prompt = input("\nYou: ")

        logger.info(f"User: {prompt}")

        if prompt.lower() in ["exit", "quit"]:
            logger.info("Sentinel Shutdown")
            print("👋 Goodbye, DGT!")
            break

        if prompt.lower() == "/clear":
            center.ai.conversation.clear()
            logger.info("Conversation Cleared")
            print("🧹 Conversation cleared.")
            continue

        response = center.process(prompt)

        logger.info(f"Sentinel: {response}")

        print(f"\nSentinel:\n{response}")


if __name__ == "__main__":
    main()