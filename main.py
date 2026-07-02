from ai.engine import AIEngine

def main():
    print("🛡️ Sentinel OS")
    print("=" * 40)

    ai = AIEngine()

    while True:
        prompt = input("\nYou: ")

        if prompt.lower() in ["exit", "quit"]:
            break

        answer = ai.ask(prompt)

        print(f"\nSentinel: {answer}")


if __name__ == "__main__":
    main()