"""The study's prompts, verbatim, and the message templates that carry them.

Paper 0 (raiLPminer) reports its prompts in Section 3.2.2 and Table 2. The
2025 harness never sent them: it passed ``systemprompt=`` to the agent
constructor, which the library swallowed without an error, so no run received
a system prompt (ADR-0001). This module is therefore the single source of truth
for what the 2026 rerun sends. The texts below are the published texts; the
only deliberate departures are listed in :data:`DEPARTURES` and printed in the
paper's prompt appendix.

Every run record stores :func:`prompt_fingerprint`, so a reader can check that
the prompts a run used are the prompts printed here.
"""

from __future__ import annotations

import hashlib
import json

#: Bump whenever any text below changes; stored in every run record.
PROMPT_VERSION = "2026.10.1"

#: The general system prompt every workflow shares (Paper 0, Section 3.2.2).
GENERAL_SYSTEM = (
    "Inspired by the provided input: Generate a complete, linear model with variables, "
    "objective function and constraints. The MILP should be described completely with "
    "equations and assumptions. The input is inspiration, so keep close to it, if you can "
    "and if information is missing, make reasonable assumptions and mark them as such. "
    "Do not ask questions."
)

#: The general call prompt that opens the conversation; the paper's input follows it.
GENERAL_CALL = (
    "Based on your input, generate a complete, linear model with variables, "
    "objective function and constraints."
)

#: Workflow-specific additions to the system prompt (Table 2, column 2).
CFC_SYSTEM_ADDITION = (
    "Use the following approach for your task: Use the or_coder to generate a code-based "
    "model based on the provided input. Interpret the code and just return the equations for "
    "objective functions, variables and constraints as text. Do not return any code."
)
OE_SYSTEM_ADDITION = (
    "Use the following approach for your task: Use the or_operator to generate an MILP based "
    "on your input. Review the MILP and feedback improvements to the or_operator and let it "
    "try again. Just return the final model."
)
PS_SYSTEM_ADDITION = (
    "Use the or_factory to generate a model based on the provided input, then choose the best. "
    "Just return the best model."
)

#: Sub-agent prompts behind the tools (Table 2, column 4 and the table note).
CODER_CALL = (
    "Generate MILP code based on the provided description. Args: description: A description "
    "of the MILP to implement. Please generate the python or GAMS code to implement the "
    "provided model."
)
OPERATOR_SYSTEM = (
    "Based on your input, generate a complete, linear MILP with variables, objective function "
    "and constraints. Explain the elements of the model."
)
OPERATOR_CALL = "Please generate an MILP based on the provided description."
FACTORY_SYSTEM = OPERATOR_SYSTEM
#: One factory instance generates one model; the orchestrator's ``count`` sets how many
#: independent instances run (the parallelization the paper describes).
FACTORY_CALL = "Please generate an MILP based on the provided description."

#: Where the 2026 texts deliberately differ from the 2025 paper, and why.
DEPARTURES: tuple[str, ...] = (
    "Parallelization-Selection: the paper describes a self-selected number of parallel "
    "Zero-Shot instances, the 2025 code asked one instance for a list of models. The rerun "
    "follows the paper: the orchestrator's count starts that many independent factory "
    "instances, each with FACTORY_CALL (one model per instance).",
    "The 2025 table shows the operator's system prompt and call prompt run together; the "
    "rerun sends them as two messages (OPERATOR_SYSTEM, OPERATOR_CALL).",
)


#: The tools the orchestrators may call; descriptions are part of the prompt surface.
TOOLS: dict[str, dict] = {
    "or_coder": {
        "type": "function",
        "function": {
            "name": "or_coder",
            "description": "Generate MILP code (python or GAMS) for the described model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "A description of the MILP to implement.",
                    }
                },
                "required": ["description"],
            },
        },
    },
    "or_operator": {
        "type": "function",
        "function": {
            "name": "or_operator",
            "description": "Generate an MILP for the described problem, or revise it after feedback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "The problem description, plus any feedback on a previous model.",
                    }
                },
                "required": ["description"],
            },
        },
    },
    "or_factory": {
        "type": "function",
        "function": {
            "name": "or_factory",
            "description": "Generate several independent MILPs for the described problem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "How many models to generate."},
                    "description": {
                        "type": "string",
                        "description": "A description of the MILP to generate.",
                    },
                },
                "required": ["count", "description"],
            },
        },
    },
}

#: Which tool each multi-step workflow exposes, and the system-prompt addition it uses.
WORKFLOW_TOOL = {"CFC": "or_coder", "OE": "or_operator", "PS": "or_factory"}
WORKFLOW_ADDITION = {
    "CFC": CFC_SYSTEM_ADDITION,
    "OE": OE_SYSTEM_ADDITION,
    "PS": PS_SYSTEM_ADDITION,
}


def system_prompt(workflow: str) -> str:
    """The orchestrator's (or the single agent's) system prompt for ``workflow``."""
    if workflow == "ZS":
        return GENERAL_SYSTEM
    return GENERAL_SYSTEM + " " + WORKFLOW_ADDITION[workflow]


def opening_message(paper_text: str) -> str:
    """The first user message: the general call prompt, then the paper's input text."""
    return f"{GENERAL_CALL}\n\n{paper_text.strip()}"


def tool_message(prompt: str, description: str) -> str:
    """A sub-agent's user message: its call prompt, then the orchestrator's description."""
    return f"{prompt}\n\n{description.strip()}"


def prompt_fingerprint() -> dict[str, str]:
    """SHA-256 of every prompt text and tool schema, keyed by name, plus the version."""
    texts = {
        "GENERAL_SYSTEM": GENERAL_SYSTEM,
        "GENERAL_CALL": GENERAL_CALL,
        "CFC_SYSTEM_ADDITION": CFC_SYSTEM_ADDITION,
        "OE_SYSTEM_ADDITION": OE_SYSTEM_ADDITION,
        "PS_SYSTEM_ADDITION": PS_SYSTEM_ADDITION,
        "CODER_CALL": CODER_CALL,
        "OPERATOR_SYSTEM": OPERATOR_SYSTEM,
        "OPERATOR_CALL": OPERATOR_CALL,
        "FACTORY_SYSTEM": FACTORY_SYSTEM,
        "FACTORY_CALL": FACTORY_CALL,
        "TOOLS": json.dumps(TOOLS, sort_keys=True),
    }
    out = {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in texts.items()}
    out["version"] = PROMPT_VERSION
    return out
