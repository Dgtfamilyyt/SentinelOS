"""
===========================================
Sentinel OS
Model Profiles

Author: DGT

Defines every AI model available
inside Sentinel OS.
===========================================
"""

MODELS = {

    "general": {
        "name": "qwen3:4b",
        "role": "General Assistant",
        "description": "Fast everyday conversations and simple reasoning.",
        "specialties": [
            "chat",
            "math",
            "general",
            "summarization"
        ]
    },

    "planner": {
        "name": "WhiteRabbitNeo/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B:latest",
        "role": "Planner & Coder",
        "description": "Planning, JSON generation, coding and tool selection.",
        "specialties": [
            "planning",
            "coding",
            "json",
            "tools"
        ]
    },

    "cyber": {
        "name": "CyberCrew/notmythos-8b:latest",
        "role": "Cybersecurity Specialist",
        "description": "Cybersecurity analysis and secure coding.",
        "specialties": [
            "linux",
            "networking",
            "malware",
            "pentesting",
            "incident_response",
            "secure_coding"
        ]
    },

    "deep": {
        "name": "qwen3.6:latest",
        "role": "DeepThink",
        "description": "Complex reasoning and long-form analysis.",
        "specialties": [
            "research",
            "architecture",
            "deep_reasoning"
        ]
    }
}