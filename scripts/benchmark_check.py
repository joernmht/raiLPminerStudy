"""A small external check: the five generators on two public modeling benchmarks.

    set -a; . ~/.config/raiLP/secrets.env; set +a
    python3 scripts/benchmark_check.py fetch          # pinned downloads into data/ (not in git)
    python3 scripts/benchmark_check.py draw           # the sample (seeded)
    python3 scripts/benchmark_check.py run <model>    # one model at a time (ScaDS: never two)
    python3 scripts/benchmark_check.py report

Paper 0's instrument has no single right answer, so it cannot be scored against a benchmark.
This check asks a narrower question with the benchmarks' own protocol: given a word problem
with all data, does a generator write a PuLP model whose optimal objective matches the label?
One attempt per item, no repair, the generators' study settings (minimal reasoning).

It is also a check of the benchmarks. Xiao et al. (2025, arXiv 2508.10047) had experts audit
them and published cleaned versions (LLM4OR). We sample items whose label they kept and items
they corrected (NL4Opt) or removed (IndustryOR), and score each answer against the original
label and, where one exists, the cleaned label. If a benchmark score moves with the label
version, a reported accuracy measures the labels as much as the models.

Benchmark texts are not committed (no or non-commercial licences): ``fetch`` downloads them at
pinned commits into ``data/``; records keep item ids, the generated code and the outcome.
Decided 2026-11-07 (Joern: "do a small one for Paper 0").
"""

from __future__ import annotations

import dataclasses
import glob
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import PacingSpec, load_study
from genstudy.llm import ChatClient

STUDY = "studies/paper0_2026/study.toml"
OUT = Path(__file__).resolve().parent.parent / "studies" / "benchmark_2026"
DATA = OUT / "data"
SEED = 20261107
PROMPT_VERSION = "2026.11.7"
TEMPERATURE = 0.0
#: Exact match within a relative tolerance (the common protocol); 1 % reported as sensitivity.
TOL, TOL_LOOSE = 1e-4, 1e-2
NL4OPT_UNCHANGED = 27  # plus every matched item whose label the audit changed
VENV_PYTHON = Path.home() / ".venvs" / "solvecheck" / "bin" / "python"
RUN_TIMEOUT_S = 120
LLM4OR = ("LLM4OR/LLM4OR", "75962df5ddf531906fda76f8708c658114e63c0e")
ORLM = ("Cardinal-Operations/ORLM", "33bc47d0a1d1710d24ab839118bdf4cb89b9e31b")
ORIGINAL = {
    "industryor": "results/IndustryOR.q2mc_en.ORLM-LLaMA-3-8B/executed.jsonl",
    "nl4opt": "results/NL4OPT.q2mc_en.ORLM-LLaMA-3-8B/executed.jsonl",
}

SYSTEM = (
    "You are an expert in operations research. You receive an optimization problem stated in "
    "words, with all its data. Formulate it as a linear or mixed-integer linear program and "
    "implement it in Python with PuLP; use no other library than PuLP and the Python standard "
    "library. Solve with prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=60)) and print "
    "exactly one line: STATUS=<pulp.LpStatus[prob.status]> OBJECTIVE=<pulp.value(prob.objective)>."
    "\n\nAnswer with one Python code block and nothing else."
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _get(repo: tuple[str, str], path: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/{repo[0]}/{repo[1]}/{path}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        dest.write_bytes(resp.read())


def fetch(_spec) -> None:
    """Download the original labels (ORLM) and the cleaned sets (LLM4OR) at pinned commits."""
    for name, path in ORIGINAL.items():
        _get(ORLM, path, DATA / "original" / f"{name}.jsonl")
    _get(LLM4OR, "static/clean_benchmarks/IndustryOR.jsonl", DATA / "clean" / "industryor.jsonl")
    tree = json.loads(
        subprocess.run(
            ["gh", "api", f"repos/{LLM4OR[0]}/git/trees/{LLM4OR[1]}?recursive=1"],
            capture_output=True, text=True, check=True,
        ).stdout
    )  # fmt: skip
    for entry in tree["tree"]:
        m = re.fullmatch(r"static/clean_benchmarks/NL4Opt/(prob_\d+)/(description\.txt|sample\.json)",
                         entry["path"])  # fmt: skip
        if m:
            _get(LLM4OR, entry["path"], DATA / "clean" / "nl4opt" / m.group(1) / m.group(2))
    print("fetched into", DATA)


def _items() -> list[dict]:
    """Every candidate item with its original and (if any) cleaned label."""
    items = []
    clean_ior = {
        _norm(r["en_question"]): r for r in _read_jsonl(DATA / "clean" / "industryor.jsonl")
    }
    for i, r in enumerate(_read_jsonl(DATA / "original" / "industryor.jsonl")):
        c = clean_ior.get(_norm(r["en_question"]))
        items.append({
            "id": f"industryor:{i}", "benchmark": "IndustryOR", "question": r["en_question"],
            "difficulty": r.get("difficulty"), "label_original": _num(r["en_answer"]),
            "label_clean": _num(c["en_answer"]) if c else None,
            "audit": "kept" if c else "removed",
        })  # fmt: skip
    originals = {_norm(r["en_question"]): (i, r)
                 for i, r in enumerate(_read_jsonl(DATA / "original" / "nl4opt.jsonl"))}  # fmt: skip
    for d in sorted(glob.glob(str(DATA / "clean" / "nl4opt" / "prob_*"))):
        question = Path(d, "description.txt").read_text(encoding="utf-8")
        hit = originals.get(_norm(question))
        if hit is None:
            continue
        i, r = hit
        clean = _num(json.loads(Path(d, "sample.json").read_text(encoding="utf-8"))[0]["output"][0])
        orig = _num(r["en_answer"])
        same = orig is not None and clean is not None and _match(orig, clean, TOL)
        items.append({
            "id": f"nl4opt:{i}", "clean_id": Path(d).name, "benchmark": "NL4Opt",
            "question": question, "label_original": orig, "label_clean": clean,
            "audit": "kept" if same else "corrected",
        })  # fmt: skip
    return items


def draw(_spec) -> None:
    items = _items()
    rng = random.Random(SEED)
    sample = [i for i in items if i["benchmark"] == "IndustryOR"]
    nl = [i for i in items if i["benchmark"] == "NL4Opt"]
    sample += [i for i in nl if i["audit"] == "corrected"]
    sample += rng.sample([i for i in nl if i["audit"] == "kept"], NL4OPT_UNCHANGED)
    for item in sample:
        item["question_sha256"] = hashlib.sha256(item["question"].encode("utf-8")).hexdigest()
    public = [{k: v for k, v in i.items() if k != "question"} for i in sample]
    doc = {"seed": SEED, "prompt_version": PROMPT_VERSION, "sources": {"llm4or": LLM4OR,
           "orlm": ORLM}, "items": public}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")  # fmt: skip
    print(Counter((i["benchmark"], i["audit"]) for i in sample))


def _code(content: str) -> str | None:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, flags=re.S)
    if blocks:
        return max(blocks, key=len)
    return content if "import pulp" in content else None


def _execute(code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "model.py"
        script.write_text(code, encoding="utf-8", newline="\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
        start = time.monotonic()
        try:
            proc = subprocess.run([str(VENV_PYTHON), "-I", str(script)], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=RUN_TIMEOUT_S)  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"outcome": "timeout"}
    found = re.findall(r"STATUS=(\S+(?: \S+)?) OBJECTIVE=(\S+)", proc.stdout)
    if proc.returncode != 0:
        outcome = "code_error"
    elif not found:
        outcome = "no_status"
    else:
        outcome = found[-1][0].lower().replace(" ", "_")
    return {
        "outcome": outcome,
        "objective": _num(found[-1][1]) if found else None,
        "stderr_tail": proc.stderr[-800:],
        "runtime_s": round(time.monotonic() - start, 1),
    }


#: MiniMax-M3 left ScaDS before this check (HTTP 403, 2026-11-07): the same model via OpenRouter,
#: with the study's reasoning setting in OpenRouter's notation (as ADR-0004 did for two models).
OVERRIDES = {
    "minimax": {
        "served_id": "minimax/minimax-m3",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "extra": {"reasoning": {"effort": "low"}, "usage": {"include": True}},
    }
}


def _model(spec, model: str):
    m = spec.models[model]
    o = OVERRIDES.get(model)
    return dataclasses.replace(m, **o) if o else m


def _client(spec, model: str) -> ChatClient:
    m = _model(spec, model)
    key = os.environ.get(m.api_key_env or spec.api_key_env)
    if not key:
        sys.exit("API key not set (set -a; . ~/.config/raiLP/secrets.env; set +a)")
    pacing = PacingSpec(min_interval_s=3.0, max_requests_per_day=400, request_timeout_s=600.0,
                        max_tries=4)  # fmt: skip
    return ChatClient(m.base_url or spec.base_url, key, pacing=pacing,
                      counter_path=OUT / f"requests_per_day.{model}.json")  # fmt: skip


def run(spec, model: str) -> None:
    items = {i["question_sha256"]: i for i in _items_with_text()}
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["items"]
    path = OUT / "runs" / f"{model}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["id"] for r in _read_jsonl(path)}
    m = _model(spec, model)
    client = _client(spec, model)
    limit = int(os.environ.get("LIMIT", "0")) or None
    todo = [i for i in sample if i["id"] not in done][:limit]
    for item in todo:
        question = items[item["question_sha256"]]["question"]
        body = {"model": m.served_id, "temperature": TEMPERATURE, "seed": SEED,
                "max_tokens": m.max_tokens,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": question}], **dict(m.extra)}  # fmt: skip
        call = client.complete(body, describe=f"{model} {item['id']}")
        code = _code(call.content)
        result = _execute(code) if code else {"outcome": "no_code", "objective": None}
        record = call.to_record()
        record["request"].pop("messages", None)  # the benchmark text stays out of the record
        _append(path, {"id": item["id"], "model": model, "prompt_version": PROMPT_VERSION,
                       "question_sha256": item["question_sha256"], "code": code,
                       "call": record, "result": result})  # fmt: skip
        print(f"{model} {item['id']}: {result['outcome']} {result.get('objective')}", flush=True)


def _items_with_text() -> list[dict]:
    out = []
    for i in _items():
        i["question_sha256"] = hashlib.sha256(i["question"].encode("utf-8")).hexdigest()
        out.append(i)
    return out


def _match(value: float | None, label: float | None, tol: float) -> bool:
    if value is None or label is None:
        return False
    return abs(value - label) <= tol * max(1.0, abs(label))


def report(spec) -> None:
    sample = {
        i["id"]: i for i in json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["items"]
    }
    rows = []
    for model in spec.models:
        for r in _read_jsonl(OUT / "runs" / f"{model}.jsonl"):
            it = sample[r["id"]]
            obj = r["result"].get("objective")
            rows.append({
                "id": r["id"], "model": model, "benchmark": it["benchmark"], "audit": it["audit"],
                "outcome": r["result"]["outcome"], "objective": obj,
                "ok_original": _match(obj, it["label_original"], TOL),
                "ok_clean": _match(obj, it["label_clean"], TOL),
                "ok_original_loose": _match(obj, it["label_original"], TOL_LOOSE),
            })  # fmt: skip
    summary: dict = {"n_answers": len(rows), "tolerance": TOL, "models": list(spec.models)}
    cells = defaultdict(lambda: Counter())
    for r in rows:
        for key in [(r["benchmark"], r["audit"]), (r["benchmark"], "all")]:
            c = cells[key]
            c["n"] += 1
            c["ok_original"] += r["ok_original"]
            c["ok_clean"] += r["ok_clean"]
            c["ok_original_loose"] += r["ok_original_loose"]
            c["runs"] += r["outcome"] == "optimal"
    summary["cells"] = {f"{b}|{a}": dict(c) for (b, a), c in sorted(cells.items())}
    per_model = defaultdict(Counter)
    for r in rows:
        c = per_model[(r["model"], r["benchmark"])]
        c["n"] += 1
        c["ok_original"] += r["ok_original"]
        # the score on the cleaned benchmark: only items with a cleaned label
        if sample[r["id"]]["label_clean"] is not None:
            c["n_clean"] += 1
            c["ok_clean"] += r["ok_clean"]
    summary["per_model"] = {f"{m}|{b}": dict(c) for (m, b), c in sorted(per_model.items())}
    # Consensus against the label: items where >= 3 of the 5 generators agree on one value
    # that is not the original label (a sign that the label, not the models, is off).
    by_item = defaultdict(list)
    for r in rows:
        if r["objective"] is not None and r["outcome"] == "optimal":
            by_item[r["id"]].append(r["objective"])
    consensus = Counter()
    for iid, values in by_item.items():
        it = sample[iid]
        groups = Counter(round(v, 4) for v in values)
        value, count = groups.most_common(1)[0]
        if count >= 3 and not _match(value, it["label_original"], TOL):
            consensus[(it["benchmark"], it["audit"])] += 1
            if it["label_clean"] is not None and _match(value, it["label_clean"], TOL):
                consensus[(it["benchmark"], it["audit"], "equals_clean")] += 1
    summary["consensus_against_original"] = {"|".join(k): v for k, v in sorted(consensus.items())}
    # The corrected NL4Opt labels: which label does the majority of the models (>= 3) reproduce,
    # and how many corrections only round a value (the text leaves integrality open)?
    sides = Counter()
    for iid, it in sample.items():
        if it["audit"] != "corrected":
            continue
        o, c = it["label_original"], it["label_clean"]
        if o is not None and c is not None and abs(o) < 1e5 and abs(o - c) < 1:
            sides["rounding"] += 1
        values = by_item.get(iid, [])
        n_clean = sum(_match(v, c, TOL) for v in values)
        n_orig = sum(_match(v, o, TOL) for v in values)
        side = "clean" if n_clean >= 3 else "original" if n_orig >= 3 else "neither"
        sides[side] += 1
    summary["nl4opt_corrected_majority"] = dict(sides)
    summary["items"] = dict(Counter(f"{i['benchmark']}|{i['audit']}" for i in sample.values()))
    _macros(summary, rows, sample, list(spec.models))
    (OUT / "report.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")  # fmt: skip
    print(json.dumps(summary, indent=1, sort_keys=True))


def _pct(k: int, n: int) -> str:
    return f"{100 * k / n:.0f}" if n else "--"


def _macros(summary: dict, rows: list[dict], sample: dict, models: list[str]) -> None:
    """Paper 0's numbers of this check (generated/benchmark_macros.tex; never edit by hand)."""
    c = summary["cells"]
    items = summary["items"]
    m = {
        "bmItems": len(sample), "bmModels": len(models), "bmAnswers": len(rows),
        "bmIOR": items.get("IndustryOR|kept", 0) + items.get("IndustryOR|removed", 0),
        "bmIORkept": items.get("IndustryOR|kept", 0), "bmIORremoved": items.get("IndustryOR|removed", 0),
        "bmNL": items.get("NL4Opt|kept", 0) + items.get("NL4Opt|corrected", 0),
        "bmNLkept": items.get("NL4Opt|kept", 0), "bmNLcorrected": items.get("NL4Opt|corrected", 0),
        "bmTolerance": f"{TOL:.0e}".replace("e-0", "e-").replace("1e-", "10^{-") + "}",
        "bmRunsShare": _pct(sum(r["outcome"] == "optimal" for r in rows), len(rows)),
    }  # fmt: skip
    for key, name in [("IndustryOR|kept", "IORkept"), ("IndustryOR|removed", "IORremoved"),
                      ("IndustryOR|all", "IORall"), ("NL4Opt|kept", "NLkept"),
                      ("NL4Opt|corrected", "NLcorr")]:  # fmt: skip
        cell = c.get(key, {})
        m[f"bmAcc{name}"] = _pct(cell.get("ok_original", 0), cell.get("n", 0))
        m[f"bmAccLoose{name}"] = _pct(cell.get("ok_original_loose", 0), cell.get("n", 0))
    cell = c.get("NL4Opt|corrected", {})
    m["bmAccCleanNLcorr"] = _pct(cell.get("ok_clean", 0), cell.get("n", 0))
    # Per model: the score on the original items vs on the cleaned items, both benchmarks.
    scores = {}
    for model in models:
        for bench, tag in [("IndustryOR", "IOR"), ("NL4Opt", "NL")]:
            pm = summary["per_model"].get(f"{model}|{bench}", {})
            scores[(model, tag)] = (
                100 * pm.get("ok_original", 0) / pm["n"] if pm.get("n") else None,
                100 * pm.get("ok_clean", 0) / pm["n_clean"] if pm.get("n_clean") else None,
            )
    for tag in ["IOR", "NL"]:
        orig = [scores[(mm, tag)][0] for mm in models if scores[(mm, tag)][0] is not None]
        clean = [scores[(mm, tag)][1] for mm in models if scores[(mm, tag)][1] is not None]
        if orig and clean:
            m[f"bm{tag}OrigMin"], m[f"bm{tag}OrigMax"] = f"{min(orig):.0f}", f"{max(orig):.0f}"
            m[f"bm{tag}CleanMin"], m[f"bm{tag}CleanMax"] = f"{min(clean):.0f}", f"{max(clean):.0f}"
            ranks_o = sorted(models, key=lambda mm: -(scores[(mm, tag)][0] or -1))
            ranks_c = sorted(models, key=lambda mm: -(scores[(mm, tag)][1] or -1))
            m[f"bm{tag}RankSame"] = "yes" if ranks_o == ranks_c else "no"
    cons = summary["consensus_against_original"]
    m["bmConsIORremoved"] = cons.get("IndustryOR|removed", 0)
    m["bmConsIORkept"] = cons.get("IndustryOR|kept", 0)
    m["bmConsNLcorr"] = cons.get("NL4Opt|corrected", 0)
    m["bmConsNLcorrClean"] = cons.get("NL4Opt|corrected|equals_clean", 0)
    m["bmConsNLkept"] = cons.get("NL4Opt|kept", 0)
    sides = summary["nl4opt_corrected_majority"]
    m["bmCorrRounding"] = sides.get("rounding", 0)
    m["bmCorrMajClean"] = sides.get("clean", 0)
    m["bmCorrMajOrig"] = sides.get("original", 0)
    m["bmCorrMajNeither"] = sides.get("neither", 0)
    n_no_code = sum(
        r["outcome"] in ("no_code", "no_status") for r in rows if r["model"] == "minimax"
    )
    m["bmMinimaxNoCode"] = n_no_code
    lines = ["% Generated by raiLPminerStudy scripts/benchmark_check.py report; do not edit."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(m.items())]
    table = ["\\begin{tabular}{lrrrr}", "\\toprule",
             " & \\multicolumn{2}{c}{IndustryOR} & \\multicolumn{2}{c}{NL4Opt} \\\\",
             "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
             "Model & original & cleaned & original & cleaned \\\\", "\\midrule"]  # fmt: skip
    names = {"glmflash": "GLM-5.3-Flash", "deepseek": "DeepSeek-V4.1-Flash", "gptoss": "gpt-oss-120b",
             "qwen": "Qwen3.8-27B", "minimax": "MiniMax-M3"}  # fmt: skip
    fmt = lambda v: "--" if v is None else f"{v:.0f}"  # noqa: E731
    for model in models:
        io, ic = scores[(model, "IOR")]
        no, nc = scores[(model, "NL")]
        table.append(
            f"{names.get(model, model)} & {fmt(io)} & {fmt(ic)} & {fmt(no)} & {fmt(nc)} \\\\"
        )
    table += ["\\bottomrule", "\\end{tabular}"]
    (OUT / "benchmark_macros.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT / "tab_benchmark.tex").write_text("\n".join(table) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    steps = {"fetch": fetch, "draw": draw, "report": report}
    if len(sys.argv) < 2 or sys.argv[1] not in [*steps, "run"]:
        sys.exit(__doc__)
    spec = load_study(STUDY)
    if sys.argv[1] == "run":
        run(spec, sys.argv[2])
    else:
        steps[sys.argv[1]](spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
