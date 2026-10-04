# Input texts: attribution and licences

Each `Pn.md` is exactly the text the models receive: the paper's abstract, the word
"Introduction" and the paper's introduction, unchanged apart from the extraction
(citation markers kept as text; floats, footnotes and page furniture removed). Title and
authors are deliberately not part of the input. The texts are redistributed under the
papers' own licences; the selection rule is docs/adr/0002.

| Key | Paper | Licence | Source of the text | Extraction |
|---|---|---|---|---|
| P1 | Shi, L., Yang, X., Zhang, W., Sun, H., Laporte, G. (2026). Integrated optimization of train rescheduling and speed management during partial blockages: a decomposition approach. *Transportation Science* 60, 484-507. https://doi.org/10.1287/trsc.2025.0137 | CC BY (accepted manuscript, University of Bath) | accepted manuscript, University of Bath Research Portal, file `2026.02.20.Manuscript-TS-2025-0137_Final_version_-260221.pdf` (SHA-256 `027cdd764e515bcdd4d2251d672ebd502b6618f788d44ffcc1e6534ec94cd13b`, downloaded 2026-10-04) | `scripts/extract_input_pdftext.py` (markers: `Abstract. `/Key words:, Introduction/Related Works; the running header naming title and authors dropped with `--drop`) |
| P2 | Versluis, N. D., Pellegrini, P., Quaglietta, E., Goverde, R. M. P., Rodriguez, J. (2025). Conflict detection and resolution for distance-to-go railway signalling. *Transportmetrica A: Transport Science*, 1-33. https://doi.org/10.1080/23249935.2025.2592225 | CC BY 4.0 | authors' deposit HAL hal-05406349 of the CC BY article | `scripts/extract_input_pdftext.py` (markers: Abstract/Keywords, Introduction/Conflict detection and resolution modelling) |
| P3 | Zhu, J. H., Dollevoet, T., Huisman, D. (2025). An exact and heuristic framework for rolling stock rescheduling with railway infrastructure availability constraints. *Transportation Research Part B* 195, 103189. https://doi.org/10.1016/j.trb.2025.103189 | CC BY 4.0 | Elsevier full-text XML | `scripts/extract_input.py` |
| P4 | Liu, X., Oliveira da Silva, C., Dabiri, A., Wang, Y., De Schutter, B. (2026). Learning-based model predictive control for passenger-oriented train rescheduling with flexible train composition. *Transportation Research Part C* 191, 105841. https://doi.org/10.1016/j.trc.2026.105841 | CC BY 4.0 | Elsevier full-text XML | `scripts/extract_input.py` |
| P5 | Lövétei, I., Lindenmaier, L., Aradi, Sz. (2025). Efficient real-time rail traffic optimization: decomposition of rerouting, reordering, and rescheduling problems. *Journal of Rail Transport Planning & Management* 33, 100496. https://doi.org/10.1016/j.jrtpm.2024.100496 | CC BY-NC 4.0 | Elsevier full-text XML | `scripts/extract_input.py` |
