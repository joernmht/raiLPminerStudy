"""raiLPminer study (2026): the rerun of Paper 0's experiment, built to be checkable.

Paper 0 (*raiLPminer: LLM-driven optimization model mining for railway
rescheduling and the case for deterministic structural validation*) generates
MILP formulations from the abstract and introduction of railway rescheduling
papers with four workflows (Zero-Shot, Code-First-Chain, Operator-Expert,
Parallelization-Selection), turns each answer into a variable-equation graph
(LP2Graph) and filters and selects on structural metrics.

The 2025 harness did not send the system prompts or temperatures it reported
(docs/adr/0001). This package re-implements the study as explicit, logged code
paths:

* :mod:`genstudy.config`    the study spec (one TOML file)
* :mod:`genstudy.prompts`   the prompts, verbatim, fingerprinted
* :mod:`genstudy.llm`       paced, retried requests; the body sent is on the record
* :mod:`genstudy.workflows` ZS / CFC / OE / PS, first tool call forced
* :mod:`genstudy.runner`    the design, run model by model, resumable
* :mod:`genstudy.notation`  the deterministic notation gate (before graphing)
* :mod:`genstudy.graphing`  LP2Graph as in Paper 0: an LLM fills a fixed schema
* :mod:`genstudy.instrument` test cases with known structure that score the parser
* :mod:`genstudy.metrics`   completeness, coherence, linearity, size, ratio, diameter

It deliberately does not use the lp2graph library: that library is the
deterministic successor (Paper 1), not the instrument Paper 0 describes.
"""

from __future__ import annotations

__version__ = "0.1.0"
