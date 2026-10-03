"""
main.py — Sentinel OS entry point

Supports two interaction modes:
  Default:  Single-step chat/tool dispatch (existing)
  /agent:   Agentic loop mode — submit a multi-step goal

Commands:
  /clear    — clear conversation history
  /agent    — start an agent goal (multi-step execution)
  /status   — show current agent state
  /stop     — interrupt a running agent task
  /targets  — list authorized lab targets
  exit/quit — shutdown
"""

from core.banner import show_banner
from core.command_center import CommandCenter
from core.logger import logger


def main():
    show_banner()
    logger.info("Sentinel OS Started")

    center = CommandCenter()

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye, DGT!")
            break

        if not prompt:
            continue

        logger.info(f"User: {prompt}")

        # ── Built-in commands ──────────────────────────────────────────

        if prompt.lower() in ("exit", "quit"):
            logger.info("Sentinel Shutdown")
            print("👋 Goodbye, DGT!")
            break

        if prompt.lower() == "/clear":
            center.ai.conversation.clear() if hasattr(center.ai, "conversation") else center.ai.clear()
            logger.info("Conversation Cleared")
            print("🧹 Conversation cleared.")
            continue

        if prompt.lower() == "/status":
            state = center.agent_state
            print(f"\n🤖 Agent Status: {'RUNNING' if state['is_running'] else 'IDLE'}")
            if state.get("active_task"):
                t = state["active_task"]
                print(f"   Task: {t['task_id'][:8]} | {t['status']} | {t['goal'][:60]}")
            print(f"   History: {state.get('task_history_count', 0)} completed tasks")
            continue

        if prompt.lower() == "/stop":
            stopped = center.stop_agent()
            print("⛔ Agent stopped." if stopped else "ℹ No agent running.")
            continue

        if prompt.lower() == "/targets":
            targets = center.authorized_targets
            if targets:
                print("\n🎯 Authorized Lab Targets:")
                for t in targets:
                    print(f"   [{t['auth_level'].upper()}] {t['label']}: {', '.join(t['targets'])}")
            else:
                print("ℹ No lab targets configured. Edit config/authorized_targets.yaml")
            continue

        # ── Agent mode ─────────────────────────────────────────────────
        if prompt.lower().startswith("/agent "):
            goal = prompt[7:].strip()
            if not goal:
                print("Usage: /agent <your goal>")
                continue

            print(f"\n🤖 Sentinel Agent starting...\n   Goal: {goal}\n")
            print("─" * 60)

            for event in center.run_agent_stream(goal=goal, mode="chat"):
                _print_event(event)

            print("─" * 60)
            continue

        # ── Default single-step mode ───────────────────────────────────
        response = center.process(prompt)
        logger.info(f"Sentinel: {response}")

        if isinstance(response, dict):
            if response.get("success"):
                print(f"\nSentinel:\n{response.get('result', response)}")
            else:
                print(f"\nSentinel [Error]: {response.get('error', 'Unknown error')}")
        else:
            print(f"\nSentinel:\n{response}")


def _print_event(event: dict) -> None:
    """Pretty-print an agent loop event to the CLI."""
    t = event.get("type", "")

    if t == "planning":
        print(f"  🧠 Planning...")
    elif t == "plan_ready":
        count = event.get("count", 0)
        replan = " (replan)" if event.get("replan") else ""
        print(f"  📋 Plan ready{replan}: {count} step(s)")
        for step in event.get("steps", []):
            print(f"      [{step.get('step_index', '?')}] {step.get('description', '')} → {step.get('tool_name', '?')}")
    elif t == "step_start":
        print(f"\n  ▶ Step [{event.get('step_index', '?')}]: {event.get('description', '')}")
        print(f"      tool: {event.get('tool', '?')}")
    elif t == "step_result":
        ok = event.get("success", False)
        icon = "✓" if ok else "✗"
        msg = str(event.get("output", ""))[:200] if ok else str(event.get("error", ""))
        print(f"      {icon} {msg}")
    elif t == "observation":
        print(f"      💡 {event.get('observation', '')[:150]}")
    elif t == "verify_start":
        print(f"      🔍 Verifying: {event.get('condition', '')}")
    elif t == "verify_result":
        status = event.get("status", "?")
        icon   = "✓" if status == "passed" else "✗"
        print(f"      {icon} Verification: {status} — {event.get('detail', '')[:100]}")
    elif t == "recovery_start":
        print(f"  ⚠  Recovery triggered [{event.get('failure_class', '?')}]")
    elif t == "recovery_result":
        print(f"      Action: {event.get('action', '?')} — {event.get('detail', '')[:100]}")
    elif t == "replan":
        print(f"  ↺  Replanning (attempt {event.get('attempt', '?')})...")
    elif t == "blocked":
        print(f"\n  ⛔ BLOCKED: {event.get('reason', '')}")
    elif t == "error":
        print(f"\n  ❌ ERROR: {event.get('message', '')}")
    elif t == "cancelled":
        print(f"\n  🛑 CANCELLED: {event.get('reason', '')}")
    elif t == "loop_complete":
        status = event.get("status", "?")
        print(f"\n  {'✅' if status == 'completed' else '❌'} {event.get('conclusion', 'Done.')}")
    elif t == "report":
        print(event.get("text", ""))
    elif t == "task_complete":
        pass  # report already printed


if __name__ == "__main__":
    main()