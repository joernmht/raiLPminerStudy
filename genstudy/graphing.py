"""LP2Graph as Paper 0 describes it: a language model fills a fixed schema.

Paper 0 (Section 3.3) turns a generated answer into a variable-equation graph
by asking a model to fill a class structure (Model, Variable, ObjectiveFunction,
Constraint, each equation listing the numbers of the variables it contains).
This module keeps that design and its field names, and changes three things
the 2025 audit showed were needed (docs/adr/0001):

1. **An exit.** ``ContainsFormulation`` lets the parser say that the text
   states no mathematical model. The 2025 schema had no such field, and the
   parser built complete graphs for 233 prose answers.
2. **The objective may be missing.** ``objective_functions`` is a list (0, 1 or
   more). The 2025 schema required exactly one objective, so a missing
   objective could not be observed.
3. **Two facts the structure needs.** ``Domain`` per variable and ``Linear``
   per equation, so that the analysis can tell a MILP from an LP and a linear
   model from a nonlinear one (the 2025 walkthrough model had an absolute value
   in its objective and was accepted).

The reply is constrained by a JSON schema on the server side and validated
with pydantic here; nothing is ``exec``-ed (the 2025 parser rebuilt the objects
from their Python repr with ``exec``). The parser model, its prompt and its
settings are fixed per study and validated separately (:mod:`genstudy.instrument`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from genstudy.config import GrapherSpec
from genstudy.llm import CallResult, ChatClient

GRAPHER_PROMPT_VERSION = "2026.10.3"

#: Length caps on every text field. Without them, greedy decoding under the schema
#: constraint can loop while copying an equation and run into the token limit (17 of
#: the first 40 validation parses with Gemma-4 did, schema 2026.10.1); the cap lets the
#: decoder close the string. The metrics use none of these texts.
ShortText = Annotated[str, Field(max_length=120)]
LongText = Annotated[str, Field(max_length=240)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Variable(_Strict):
    Number: int
    Abbreviation: ShortText
    Name: ShortText
    Description: LongText
    Domain: Literal["binary", "integer", "continuous", "unknown"]


class Equation(_Strict):
    Name: ShortText
    Number: int
    equation: LongText
    description: LongText
    VariablesIncluded: list[int]
    Linear: bool


class ObjectiveFunction(Equation):
    pass


class Constraint(Equation):
    pass


class Model(_Strict):
    ContainsFormulation: bool
    variablesInModel: list[Variable]
    objective_functions: list[ObjectiveFunction]
    constraints: list[Constraint]


GRAPHER_SYSTEM = (
    "You convert the text of an optimization model into a structured record. Report only "
    "what the text states as mathematics, that is, objective functions, equations and "
    "inequalities written with symbols. Do not complete, repair, improve or invent anything."
)

GRAPHER_TASK = """Read the text below and fill in the predefined form.

- ContainsFormulation: true only if the text writes out at least one objective function or constraint as a mathematical expression. False if the text only describes or outlines a model in words, discusses an approach, asks a question, or contains no model.
- variablesInModel: every decision variable that appears in the written expressions, numbered from 1. Parameters, sets and indices are not decision variables. An indexed family such as x_{ij} counts once. Domain: binary, integer or continuous as the text declares it, unknown if it does not say.
- objective_functions: every objective function written as an expression, numbered from 0, with the numbers of the decision variables it contains. Leave the list empty if no objective function is written out.
- constraints: every constraint written as an equation or inequality, numbered from 1, with the numbers of the decision variables it contains. A constraint written once for all members of a set counts once. A constraint that is only described in words is not included. Variable domain declarations alone (such as x binary) are not constraints.
- Linear: false if the expression multiplies or divides decision variables, takes an absolute value, a maximum or minimum, a logical implication or any other nonlinear function of decision variables; otherwise true.

Text:
"""


#: In ``prompt`` mode the schema travels in the prompt instead of the decoder.
PROMPT_MODE_SUFFIX = (
    "\n\nReturn only one JSON object that matches this JSON schema, without code fences:\n"
)


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Replace ``$ref``s by their definitions (some guided decoders reject ``$defs``)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


MODEL_SCHEMA: dict[str, Any] = _inline_refs(Model.model_json_schema())


def grapher_fingerprint() -> dict[str, str]:
    texts = {
        "GRAPHER_SYSTEM": GRAPHER_SYSTEM,
        "GRAPHER_TASK": GRAPHER_TASK,
        "MODEL_SCHEMA": json.dumps(MODEL_SCHEMA, sort_keys=True),
        "PROMPT_MODE_SUFFIX": PROMPT_MODE_SUFFIX,
    }
    out = {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in texts.items()}
    out["version"] = GRAPHER_PROMPT_VERSION
    return out


def grapher_body(grapher: GrapherSpec, answer: str, *, seed_offset: int = 0) -> dict[str, Any]:
    task = GRAPHER_TASK + answer.strip()
    body: dict[str, Any] = {
        "model": grapher.served_id,
        "messages": [
            {"role": "system", "content": GRAPHER_SYSTEM},
            {"role": "user", "content": task},
        ],
        "temperature": grapher.temperature,
        "seed": grapher.seed + seed_offset,
        "max_tokens": grapher.max_tokens,
    }
    if grapher.mode == "schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "lp2graph_model", "schema": MODEL_SCHEMA, "strict": True},
        }
        if grapher.whitespace_pattern is not None:
            body["guided_whitespace_pattern"] = grapher.whitespace_pattern
    elif grapher.mode == "prompt":
        body["messages"][1]["content"] = task + PROMPT_MODE_SUFFIX + json.dumps(MODEL_SCHEMA)
    else:
        raise ValueError(f"unknown grapher mode {grapher.mode!r}")
    return body


@dataclass(frozen=True)
class GraphingResult:
    model: Model | None
    call: CallResult
    error: str | None


def parse_reply(content: str) -> Model:
    """Validate a grapher reply against the schema (raises ``ValueError``)."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    try:
        return Model.model_validate_json(text)
    except ValidationError as exc:
        raise ValueError(f"reply does not match the schema: {exc.error_count()} errors") from exc


def graph_answer(
    client: ChatClient, grapher: GrapherSpec, answer: str, *, seed_offset: int = 0
) -> GraphingResult:
    """One parsing request; a reply that does not validate is a result with an error."""
    call = client.complete(
        grapher_body(grapher, answer, seed_offset=seed_offset), describe="grapher"
    )
    try:
        return GraphingResult(model=parse_reply(call.content), call=call, error=None)
    except ValueError as exc:
        return GraphingResult(model=None, call=call, error=str(exc))
