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

The reply is validated with pydantic here (in ``schema`` mode the server also
constrains the decoding); nothing is ``exec``-ed (the 2025 parser rebuilt the
objects from their Python repr with ``exec``). The parser model, its prompt and its
settings are fixed per study and validated separately (:mod:`genstudy.instrument`).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from genstudy.config import GrapherSpec
from genstudy.llm import CallResult, ChatClient

GRAPHER_PROMPT_VERSION = "2026.10.5"

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


#: In ``prompt`` mode the schema travels in the prompt instead of the decoder. It comes
#: before the text and the instruction comes last: with the schema at the end of a long
#: prompt, the parser returned the schema itself (pilot, 2026-10-04).
PROMPT_MODE_FORM = "The form, as a JSON schema:\n"
PROMPT_MODE_FINAL = (
    "\n\nReturn only the JSON object for the text above, filled in according to the form, "
    "without code fences."
)

#: In ``template`` mode the form is a JSON template with placeholders instead of a JSON
#: schema. On the long reference formulations the parser returned the schema itself in 5 of
#: 10 replies (2026-10-04); a template is not valid JSON, so an echo cannot pass as a record.
TEMPLATE_FORM = (
    "The form, as a JSON template: replace every <...> and give each list as many entries "
    "as the text requires (possibly none). Write each text field in at most 240 characters "
    "(symbols and names in at most 120) and shorten a long expression instead of copying it.\n"
    '{"ContainsFormulation": <true or false>,\n'
    ' "variablesInModel": [{"Number": <1, 2, ...>, "Abbreviation": "<symbol>", '
    '"Name": "<name>", "Description": "<description>", '
    '"Domain": "<binary, integer, continuous or unknown>"}],\n'
    ' "objective_functions": [{"Name": "<name>", "Number": <0, 1, ...>, '
    '"equation": "<expression>", "description": "<description>", '
    '"VariablesIncluded": [<variable numbers>], "Linear": <true or false>}],\n'
    ' "constraints": [{"Name": "<name>", "Number": <1, 2, ...>, '
    '"equation": "<expression>", "description": "<description>", '
    '"VariablesIncluded": [<variable numbers>], "Linear": <true or false>}]}\n'
)
TEMPLATE_FINAL = (
    "\n\nNow write the filled-in form for the text above as one JSON object, without code "
    "fences and without repeating the template."
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
        "PROMPT_MODE_FORM": PROMPT_MODE_FORM,
        "PROMPT_MODE_FINAL": PROMPT_MODE_FINAL,
        "TEMPLATE_FORM": TEMPLATE_FORM,
        "TEMPLATE_FINAL": TEMPLATE_FINAL,
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
        instructions, text_marker = GRAPHER_TASK.rsplit("Text:", 1)
        body["messages"][1]["content"] = (
            instructions
            + PROMPT_MODE_FORM
            + json.dumps(MODEL_SCHEMA)
            + "\n\nText:"
            + text_marker
            + answer.strip()
            + PROMPT_MODE_FINAL
        )
    elif grapher.mode == "template":
        instructions, text_marker = GRAPHER_TASK.rsplit("Text:", 1)
        body["messages"][1]["content"] = (
            instructions + TEMPLATE_FORM + "\nText:" + text_marker + answer.strip() + TEMPLATE_FINAL
        )
    else:
        raise ValueError(f"unknown grapher mode {grapher.mode!r}")
    return body


@dataclass(frozen=True)
class GraphingResult:
    model: Model | None
    call: CallResult
    error: str | None
    repairs: tuple[str, ...] = ()


#: Field names per object level, for the key repair in :func:`normalize_keys`.
_FIELDS: dict[str, tuple[str, ...]] = {
    "model": tuple(Model.model_fields),
    "variable": tuple(Variable.model_fields),
    "equation": tuple(Equation.model_fields),
}
_CHILDREN = {
    "variablesInModel": "variable",
    "objective_functions": "equation",
    "constraints": "equation",
}


def _canon(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def normalize_keys(obj: Any, level: str = "model", repairs: list[str] | None = None) -> Any:
    """Map reply keys onto the schema's field names, deterministically.

    The legacy schema mixes ``Name``/``VariablesIncluded`` with ``equation``/
    ``description``, and parsers answering from a schema in the prompt often
    normalise the case or copy schema keywords (``additionalProperties``). A key
    is renamed when it matches a field ignoring case and punctuation, and
    dropped when it matches none; values are never touched. Every repair is
    listed in ``repairs``.
    """
    if not isinstance(obj, dict):
        return obj
    fields = {_canon(f): f for f in _FIELDS[level]}
    out: dict[str, Any] = {}
    for key, value in obj.items():
        target = fields.get(_canon(key))
        if target is None:
            if repairs is not None:
                repairs.append(f"dropped {level}.{key}")
            continue
        if target != key and repairs is not None:
            repairs.append(f"renamed {level}.{key}")
        child = _CHILDREN.get(target) if level == "model" else None
        if child and isinstance(value, list):
            value = [normalize_keys(v, child, repairs) for v in value]
        out[target] = value
    return out


#: A lone backslash that does not start a JSON escape (LaTeX such as ``\le`` written raw).
_STRAY_BACKSLASH = re.compile(r'(?<!\\)\\(?![\\"/bfnrtu])')
#: A formula written without its key: ``"Number": 6, "<formula>", "description"``.
_MISSING_EQUATION_KEY = re.compile(r'("Number": *-?\d+, *)("(?:[^"\\]|\\.)*")(, *"description")')
#: A paper's equation label copied as the number, unquoted: ``"Number": 18a``.
_LABEL_NUMBER = re.compile(r'("Number": *-?\d+)[A-Za-z]+(?=\s*[,}])')


#: The length cap of every capped text field, per object level (read from the schema).
_CAPS: dict[str, dict[str, int]] = {
    level: {
        name: meta.max_length
        for name, field in cls.model_fields.items()
        for meta in field.metadata
        if hasattr(meta, "max_length")
    }
    for level, cls in (("variable", Variable), ("equation", Equation))
}


def _cut_long_texts(data: Any, log: list[str]) -> Any:
    """Cut text fields to their cap; the metrics read none of the texts.

    The caps keep schema-constrained decoding from looping, but a reply written from a
    prompt can exceed them when it copies a long expression (an objective of
    Zhu et al. 2025, 2026-10-04). Without this one long string fails the whole record.
    """
    if not isinstance(data, dict):
        return data
    cut = 0
    for key, level in _CHILDREN.items():
        items = data.get(key)
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            for name, cap in _CAPS[level].items():
                value = item.get(name)
                if isinstance(value, str) and len(value) > cap:
                    item[name] = value[:cap]
                    cut += 1
    if cut:
        log.append(f"cut {cut} over-long text fields")
    return data


def _echoes_schema(raw: Any) -> bool:
    return isinstance(raw, dict) and "properties" in raw and "ContainsFormulation" not in raw


def _decode(text: str, log: list[str]) -> tuple[Any, int, str]:
    """The first JSON object of ``text``, where it ends, and the text it was read from.

    Lone backslashes of raw LaTeX are escaped only when the text fails on exactly that.
    """
    try:
        raw, end = json.JSONDecoder().raw_decode(text)
        return raw, end, text
    except json.JSONDecodeError as exc:
        if "Invalid \\escape" not in exc.msg:
            raise ValueError(f"reply is not JSON: {exc.msg}") from exc
    text = _STRAY_BACKSLASH.sub(r"\\\\", text)
    log.append("escaped stray backslashes")
    try:
        raw, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not JSON: {exc.msg}") from exc
    return raw, end, text


def parse_reply(content: str, repairs: list[str] | None = None) -> Model:
    """Validate a grapher reply against the schema (raises ``ValueError``).

    Deterministic repairs, each recorded in ``repairs``: a code fence is removed,
    text after the first JSON object is ignored, a formula string written without
    its ``equation`` key is given the key back, lone backslashes of raw LaTeX are
    escaped (only when the reply fails on exactly that), the letter of an equation
    label copied as a number is dropped (``18a``; the metrics do not use equation
    numbers), an echoed schema that is followed by the filled record is skipped, keys are mapped onto the schema's
    names (:func:`normalize_keys`) and over-long text fields are cut to their cap.
    A reply that only echoes the schema is an error, not something to repair.
    """
    log = repairs if repairs is not None else []
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
        log.append("removed code fence")
    text = text[text.find("{") :] if "{" in text else text
    fixed = _LABEL_NUMBER.sub(r"\1", text)
    if fixed != text:
        log.append("dropped letters from equation numbers")
        text = fixed
    fixed = _MISSING_EQUATION_KEY.sub(r'\1"equation": \2\3', text)
    if fixed != text:
        log.append("inserted missing equation keys")
        text = fixed
    raw, end, text = _decode(text, log)
    if _echoes_schema(raw):
        rest = text[end:]
        if "{" not in rest:
            raise ValueError("reply echoes the schema instead of filling it")
        log.append("skipped an echoed schema")
        raw, end, text = _decode(rest[rest.find("{") :], log)
        if _echoes_schema(raw):
            raise ValueError("reply echoes the schema instead of filling it")
    if text[end:].strip():
        log.append("ignored text after the JSON object")
    try:
        return Model.model_validate(_cut_long_texts(normalize_keys(raw, "model", log), log))
    except ValidationError as exc:
        raise ValueError(f"reply does not match the schema: {exc.error_count()} errors") from exc


def graph_answer(
    client: ChatClient, grapher: GrapherSpec, answer: str, *, seed_offset: int = 0
) -> GraphingResult:
    """One parsing request; a reply that does not validate is a result with an error."""
    call = client.complete(
        grapher_body(grapher, answer, seed_offset=seed_offset), describe="grapher"
    )
    repairs: list[str] = []
    try:
        model = parse_reply(call.content, repairs)
    except ValueError as exc:
        return GraphingResult(model=None, call=call, error=str(exc), repairs=tuple(repairs))
    return GraphingResult(model=model, call=call, error=None, repairs=tuple(repairs))
