# ADR-0002: Input papers are chosen by a rule, and all five are new

**Status:** proposed (2026-10-04); the selected papers are confirmed by Joern before the
production runs.

## Context

The 2025 pilot read five papers (Zhan et al. 2016 TR-E; D'Ariano et al. 2008 Transp.
Sci.; Koniorczyk et al. 2025 JRTPM; Pellegrini et al. 2014 TR-B; Zhang et al. 2023 TR-B).
Four were published by Elsevier and one by INFORMS, so their abstracts and introductions
could not be published with the run records; the pilot's Zenodo record contained them
and its access is now restricted. One paper (D'Ariano et al. 2008) contains no MILP, so
it had no reference formulation. Most were older and well cited, so the models may have
seen them, including their formulations, during training.

## Decision

All five input papers are replaced (Joern, 2026-10-04: "public access, similar to the
other papers, relevant authors but low citation so adaptation risk is lower, only papers
with models"). A paper qualifies if it

1. is open access under a Creative Commons licence that permits at least non-commercial
   redistribution of its text (CC BY, CC BY-SA, CC BY-NC or CC BY-NC-ND; CC BY preferred
   at equal fit), so that the inputs can be published with the data, and is not published
   in an MDPI journal (Joern, 2026-10-04: "Don't do mdpi papers");
2. addresses real-time or operational train rescheduling or dispatching under
   disruptions or perturbations, the problem family of the pilot;
3. has at least one author with an established record in railway rescheduling;
4. has few citations and a recent publication date (lower risk that the models
   memorized it);
5. writes out an explicit MILP or ILP formulation (objective function and constraints),
   separate from an introduction that contains no formulation.

Papers co-authored by the study's authors are excluded. The licence rule was widened from
CC BY/CC BY-SA to the NC variants on 2026-10-04 (Joern), because two sub-problem slots had
only weak CC BY candidates; as a consequence the published dataset is non-commercial
(CC BY-NC 4.0), and an ND-licensed input is redistributed verbatim only. Among qualifying papers we
prefer a spread over the pilot's sub-problems (blocked line segments, real-time
reordering and rerouting, urban networks, station and junction routing, network-wide
disruptions). One paper is the anchor of experiment 1.

## The input text

`inputs/Pn.md` holds exactly the text that is sent: the abstract, a blank line, the word
"Introduction" and the introduction, with citation markers kept as in the pilot and
extraction artifacts removed. Title and authors are not part of the input (they would cue
recall); the attribution lives in `study.toml` and `inputs/README.md`. The reference
formulation is kept in `references/Pn.md` with its annotated structure in
`references/Pn.json` (the LP2Graph v2 schema), which also serve as realistic parser test
cases.

## Search and selection

The search ran on 4 October 2026 against OpenAlex: 78 phrase queries (48 on title and
abstract, 30 on the indexed full text, for example "train rescheduling", "train
dispatching", "real-time railway traffic management", "disruption management" railway),
restricted to open-access journal articles published 2023 to 2026. The record is in
`studies/paper0_2026/selection/` (OpenAlex and Crossref metadata and the screening
decisions only; no paper text):

| Step | Works left |
|---|---|
| unique works returned (`queries.json`, every query with its hit count) | 1,918 |
| title names a rescheduling or disruption term and a rail term | 257 |
| an open copy under an admitted licence (OpenAlex location record without DOAJ entries, confirmed against the Crossref record of the version of record or the repository record; `crossref_licences.json`) | 208 |
| at most 10 OpenAlex citations on 2026-10-04 | 178 |
| published 2024 to 2026 | 132 |
| not in an MDPI journal | 98 |
| manual screen of title and abstract: real-time or operational rescheduling or dispatching with an optimisation model (`screening_round1.json`, `screening_round2.json`) | 26 |

For the 26 the full text was read for criteria 3 and 5. Supplementary searches in
Crossref (12 queries) and the arXiv API (10 queries) found no further qualifying paper.
The licence check matters: OpenAlex lists three closed Elsevier papers as CC BY-NC-ND,
among them the best urban fit (Jiang et al. 2026, TR-B), whose publisher records carry
only text-and-data-mining licences.

From the qualifying papers one was chosen per sub-family of the pilot's input set, at
most one per research group, preferring in this order a closer problem fit, a cleaner
MILP, a CC BY or CC BY-SA licence on the version of record, fewer citations and a later
first public appearance (preprints included). Candidates, evidence and alternates per
slot: `shortlist_round1.json` (CC BY and CC BY-SA only) and `shortlist_round2.json`
(after the NC widening and the MDPI exclusion).

| Key | Paper | Sub-family (pilot input it replaces) | Licence of the text used | Cites | Reference formulation |
|---|---|---|---|---|---|
| P1 | Shi, Yang, Zhang, Sun, Laporte 2026, *Transp. Sci.* 60:484-507 | partial segment blockage (Zhan et al. 2016) | CC BY, accepted manuscript (Univ. of Bath); version of record closed | 1 | MILP announced in the abstract; section not yet verified |
| P2 | Versluis, Pellegrini, Quaglietta, Goverde, Rodriguez 2025, *Transportmetrica A* | junction routing and scheduling (Pellegrini et al. 2014) | CC BY 4.0 | 0 | Sect. 4.2: objective (2), constraints (3)-(18) |
| P3 | Zhu, Dollevoet, Huisman 2025, *TR Part B* 195:103189 | network-wide disruption (Zhang et al. 2023) | CC BY 4.0 | 7 | Sect. 4.1 (1)-(21) and Sect. 4.2 (22)-(36) |
| P4 | Liu, Oliveira da Silva, Dabiri, Wang, De Schutter 2026, *TR Part C* 191:105841 | urban network (Koniorczyk et al. 2025) | CC BY 4.0 | 1 | MILP-based MPC: Sect. 3 and 4.2-4.3 |
| P5 | Lövétei, Lindenmaier, Aradi 2025, *JRTPM* 33:100496 | real-time reordering and rerouting (D'Ariano et al. 2008) | CC BY-NC 4.0 | 3 | Sect. 2: constraints (1)-(26), objective (72) |

Cites = OpenAlex `cited_by_count` read on 2026-10-04. P1 anchors experiment 1 if its
written-out MILP is confirmed from the accepted manuscript (the repository blocks scripted
downloads); otherwise P2 becomes the anchor. Known weaknesses, accepted on 2026-10-04:

- P2 and P5 both descend from RECIFE-MILP, the model family of the excluded Pellegrini et
  al. 2014, so two of the five reference models share a lineage.
- P3 reschedules rolling stock; the timetable is only retimed for feasibility.
- P4's MILP is the model-predictive-control baseline in state-space notation, its
  perturbation is passenger demand rather than infrastructure, and its arXiv preprint has
  been public since February 2025.
- P5's group has two earlier real-time traffic management papers (criterion 3 only partly
  met), and its arXiv preprint has been public since September 2022.
- Two universities appear twice through different groups (TU Delft: Goverde, De Schutter;
  BJTU: Sun and Yang, Wang), which Joern accepted ("one per group is enough").
