"""
agent/factory.py
================
AgentFactory — assembles the complete agent pipeline.

Single place where all agent components are instantiated and wired together.
CommandCenter calls AgentFactory.build() to get a fully configured AgentExecutive.

Wiring:
    AgentMemory
    AgentPlanner(tool_manager, ai_client, model_router)
    StepExecutor(tool_manager)
    StateVerifier(tool_manager, ai_engine)
    FailureRecovery()
    AgentLoop(planner, executor, verifier, recovery, memory)
    AgentExecutive(loop, ...)
    AuthorizationModel()
    AgentReporter()
"""

from __future__ import annotations

from agent.memory       import AgentMemory
from agent.planner      import AgentPlanner
from agent.executor     import StepExecutor
from agent.verifier     import StateVerifier
from agent.recovery     import FailureRecovery
from agent.loop         import AgentLoop
from agent.executive    import AgentExecutive
from agent.authorization import AuthorizationModel
from agent.reporter     import AgentReporter
from agent.goal         import GoalUnderstandingEngine


def build_agent(
    tool_manager,
    ai_client,
    model_router,
    ai_engine        = None,
    max_steps:  int  = 30,
    max_retries:int  = 2,
    max_replans:int  = 3,
) -> tuple[AgentExecutive, AuthorizationModel, AgentReporter]:
    """
    Build and return the complete agent system.

    Returns:
        (AgentExecutive, AuthorizationModel, AgentReporter)
    """
    memory    = AgentMemory()
    planner   = AgentPlanner(tool_manager, ai_client, model_router)
    executor  = StepExecutor(tool_manager)
    verifier  = StateVerifier(tool_manager, ai_engine)
    recovery  = FailureRecovery()
    reporter  = AgentReporter()
    auth      = AuthorizationModel()
    goal_engine = GoalUnderstandingEngine(ai_client=ai_client, model_router=model_router)

    loop = AgentLoop(
        planner  = planner,
        executor = executor,
        verifier = verifier,
        recovery = recovery,
        memory   = memory,
    )

    executive = AgentExecutive(
        loop        = loop,
        goal_engine = goal_engine,
        max_steps   = max_steps,
        max_retries = max_retries,
        max_replans = max_replans,
    )

    return executive, auth, reporter
