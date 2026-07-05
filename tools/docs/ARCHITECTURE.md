# 🛡️ Sentinel OS

## Overview

Sentinel OS is a local AI Operating System developed by DGT.

Its purpose is to combine Large Language Models with modular tools,
memory, cybersecurity utilities and automation into a single platform.

---

# High Level Architecture

User
 │
 ▼
Command Center
 │
 ▼
Planner
 │
 ▼
Dispatcher
 │
 ▼
Tool Manager
 │
 ▼
Tools
 │
 ▼
Result
 │
 ▼
AI Engine
 │
 ▼
Response

---

# Project Structure

SentinelOS/

ai/
core/
tools/
database/
memory/
config/
plugins/
dashboard/
api/
docs/
tests/

---

# Folder Responsibilities

## ai/

Contains every AI-related component.

Files:

engine.py

Main chat engine.

planner.py

Determines what action Sentinel should perform.

prompts.py

Stores system prompts.

Future:

router.py

reasoner.py

response_builder.py

---

## core/

Central operating system.

Files:

command_center.py

Entry point for every request.

dispatcher.py

Executes plans.

logger.py

Logging.

banner.py

Startup banner.

---

## tools/

Contains every executable tool.

manager.py

Executes tools.

registry.py

Registers tools.

base.py

Abstract Tool class.

Filesystem/

Terminal/

Cyber/

Memory/

---

## database/

SQLite

Persistent storage

Conversation history

Memory

---

## memory/

Short-term memory

Long-term memory

Semantic search (future)

---

## config/

Application configuration.

Future:

models.py

settings.py

permissions.py

---

## plugins/

Future plugin system.

Each plugin can add:

Tools

Models

Commands

UI

---

## dashboard/

Future React dashboard.

---

## api/

FastAPI backend.

---

## tests/

Unit tests.

---

# Data Flow

User

↓

Command Center

↓

Planner

↓

Dispatcher

↓

Tool Manager

↓

Tool

↓

AI Engine

↓

User

---

# Design Principles

Single Responsibility

Every class has one job.

Modular

Everything is replaceable.

Scalable

Adding a feature should require minimal changes.

Local First

Sentinel should work without cloud services whenever possible.

Security

Tools execute through controlled interfaces rather than allowing arbitrary code paths.

---

# Current Status

AI Engine

✅

Planner

🟨

Dispatcher

🟨

Tool Manager

✅

Memory

🟨

Database

✅

Plugins

⬜

Dashboard

⬜

Cyber Tools

⬜