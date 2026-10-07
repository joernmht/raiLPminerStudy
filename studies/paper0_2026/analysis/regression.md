# Regressions (analysis plan, Paper 0 Section 5)

## yield_exp1: logistic, n = 888, events = 643, McFadden R2 (full) = 0.156, separated cells: glmflashxOE 44/44

| term | LR chi2 | df | p |
|---|---|---|---|
| model | 96.0 | 4 | < 0.001 |
| workflow | 25.59 | 3 | < 0.001 |
| model:workflow | 42.36 | 12 | < 0.001 |
| temperature | 2.94 | 2 | 0.230 |

odds ratios (additive model): C(workflow)[T.CFC] 0.8, C(workflow)[T.OE] 1.76, C(workflow)[T.PS] 2.19, C(temperature)[T.0.6] 0.93, C(temperature)[T.1.0] 1.29

## accepted_exp1: logistic, n = 888, events = 369, McFadden R2 (full) = 0.091, separated cells: none

| term | LR chi2 | df | p |
|---|---|---|---|
| model | 42.98 | 4 | < 0.001 |
| workflow | 23.17 | 3 | < 0.001 |
| model:workflow | 38.51 | 12 | < 0.001 |
| temperature | 7.06 | 2 | 0.029 |

odds ratios (additive model): C(workflow)[T.CFC] 2.27, C(workflow)[T.OE] 1.46, C(workflow)[T.PS] 2.28, C(temperature)[T.0.6] 1.09, C(temperature)[T.1.0] 0.7

## complexity log_size: OLS (HC3), n = 643, R2 = 0.476

| term | Wald chi2 | df | p |
|---|---|---|---|
| model | 123.84 | 4 | < 0.001 |
| workflow | 4.61 | 3 | 0.203 |
| model:workflow | 155.01 | 12 | < 0.001 |
| temperature | 6.21 | 2 | 0.045 |

## complexity log_cv: OLS (HC3), n = 643, R2 = 0.121

| term | Wald chi2 | df | p |
|---|---|---|---|
| model | 2.0 | 4 | 0.736 |
| workflow | 9.02 | 3 | 0.029 |
| model:workflow | 20.41 | 12 | 0.060 |
| temperature | 18.17 | 2 | < 0.001 |

## complexity diameter: OLS (HC3), n = 643, R2 = 0.302

| term | Wald chi2 | df | p |
|---|---|---|---|
| model | 85.5 | 4 | < 0.001 |
| workflow | 13.06 | 3 | 0.005 |
| model:workflow | 33.35 | 12 | < 0.001 |
| temperature | 2.02 | 2 | 0.365 |

## input papers (ZS, T = 0.6): n = 368, paper LR chi2 = 12.88, df = 4, p = 0.012
