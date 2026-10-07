#!/bin/bash
# Copy Paper 0's generated numbers, tables and figures into its Overleaf checkout:
#
#   scripts/export_paper.sh ~/6a7cb7f3670577d85a762b35
#
# Macros and tables go to generated/ (\input by Main.tex), figures to figures/. The
# files are produced by `python -m genstudy analyze` and scripts/{regression,
# domain_vectors,name_topics,yield_figures,paper_numbers,ablation_t0}.py; nothing is
# edited on the way.
set -eu
PAPER=${1:?usage: scripts/export_paper.sh <paper checkout>}
cd "$(dirname "$0")/.."
A=studies/paper0_2026/analysis
mkdir -p "$PAPER/generated" "$PAPER/figures"
for f in results_macros regression_macros domain_macros paper_macros ablation_macros \
         tab_yield tab_fingerprint tab_types; do
  cp "$A/$f.tex" "$PAPER/generated/$f.tex"
done
cp "$A/yield_sankey.pdf" "$PAPER/figures/fig_yield_sankey.pdf"
cp "$A/domain.pdf" "$PAPER/figures/fig_domain.pdf"
cp "$A/topics.pdf" "$PAPER/figures/fig_constraint_types.pdf"
echo "exported to $PAPER (generated/, figures/)"
