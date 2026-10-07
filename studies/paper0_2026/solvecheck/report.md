# Solvability check (pilot)

| item | kind | outcome | repairs | code: variable / constraint families | text graph: variables / constraints | note |
|---|---|---|---|---|---|---|
| exp1.P1.qwen.ZS.t06.r01 | disconnected | optimal | 0 | 52 / 19 | 14 / 16 |  |
| exp2.P3.gptoss.ZS.t06.r01 | disconnected | infeasible | 0 | 15 / 14 | 7 / 11 |  |
| exp2.P4.deepseek.ZS.t06.r15 | nonlinear | not_expressible | 0 | -- | 19 / 21 | NotImplementedError: Multiple constraints and objective terms: contain nonlinearities or non-standard formulations that PuLP cannot express |
| exp2.P5.gptoss.ZS.t06.r03 | nonlinear | code_error | 2 | -- | 7 / 11 | KeyError: 1 |
| ref:P1 | reference | not_expressible | 0 | -- | 22 / 38 | NotImplementedError: Objective function: contains absolute values and max functions that PuLP cannot express directly |
| ref:P2 | reference | code_error | 2 | -- | 10 / 16 | TypeError: string indices must be integers, not 'str' |
| ref:P3 | reference | optimal | 0 | 23 / 14 | 11 / 14 |  |
| ref:P3b | reference | optimal | 1 | 45 / 15 | 5 / 10 |  |
| ref:P4 | reference | not_expressible | 0 | -- | 20 / 24 | TypeError: '<' not supported between instances of 'LpVariable' and 'int' |
| ref:P5 | reference | code_error | 2 | -- | 12 / 26 | KeyError: ('t2', 't1', 'tc0') |
| exp1.P1.glmflash.OE.t02.r01 | usable | optimal | 1 | 40 / 68 | -- / -- |  |
| exp1.P1.glmflash.PS.t02.r15 | usable | optimal | 0 | 45 / 17 | 10 / 15 |  |
| exp1.P1.gptoss.ZS.t02.r11 | usable | optimal | 1 | 34 / 17 | 9 / 15 |  |
| exp1.P1.qwen.CFC.t10.r12 | usable | optimal | 2 | 33 / 37 | 9 / 16 |  |
| exp1.P1.qwen.OE.t10.r09 | usable | not_expressible | 2 | -- | 17 / 21 | TypeError: Non-constant expressions cannot be multiplied |
| exp2.P3.gptoss.ZS.t06.r08 | usable | infeasible | 0 | 23 / 15 | 9 / 11 |  |
| exp2.P4.deepseek.ZS.t06.r14 | usable | code_error | 2 | -- | 16 / 32 | KeyError: (1, 2, 2) |
| exp2.P4.minimax.ZS.t06.r08 | usable | optimal | 0 | 128 / 29 | 15 / 23 |  |
| exp2.P5.deepseek.ZS.t06.r07 | usable | infeasible | 1 | 25 / 14 | 6 / 13 |  |
| exp2.P5.minimax.ZS.t06.r13 | usable | optimal | 1 | 38 / 17 | 8 / 18 |  |

{
 "disconnected": {
  "optimal": 1,
  "infeasible": 1
 },
 "nonlinear": {
  "not_expressible": 1,
  "code_error": 1
 },
 "reference": {
  "not_expressible": 2,
  "code_error": 2,
  "optimal": 2
 },
 "usable": {
  "optimal": 6,
  "not_expressible": 1,
  "infeasible": 2,
  "code_error": 1
 }
}
