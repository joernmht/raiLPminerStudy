# Nonlinear cores: random sample of 40 of 287 (seed 2026)

## exp1.P1.glmflash.ZS.t10.r05: 1 of 11 equations marked

- **Same-track headway**: `t^{dep}_{g,i} >= t^{arr}_{f,i+1} + h - M(1-o_{fgi}) - M|y_{fi}-y_{gi}|*I[i not in B]`
  variables: t^{arr}_{fs} (integer), t^{dep}_{fs} (integer), o_{fgi} (binary), y_{fi} (binary)

## exp1.P1.minimax.PS.t02.r08: 1 of 24 equations marked

- **C16**: `y_{i,b^*,k^{blk},t} \le 1 - r_{i,b^*}, y_{i,b^*,k^{opp},t} \ge r_{i,b^*}(y_{i,b^*,k^{blk},t} + y_{i,b^*,k^{opp},t})`
  variables: y_{i,b,k,t} (binary), r_{i,b} (binary)

## exp2.P4.glmflash.ZS.t06.r15: 2 of 14 equations marked

- **Passenger balance**: `b_{i,k} + w_{i,k} = w_{i-1,k} + \sum q_{k}^{\ell} (\dots)^{+}`
  variables: w_{i,k} (continuous), b_{i,k} (continuous)
- **Waiting time definition**: `W_k = \sum b_{i,k}(d_{i,k} - \hat{d}_{i,k}) + \gamma L_k`
  variables: b_{i,k} (continuous), d_{i,k} (continuous), W_k (continuous), L_k (continuous)

## exp2.P4.gptoss.ZS.t06.r11: 1 of 16 equations marked

- **Capacity**: `sum_{t,k} beta_k*y_{t,k}*(sum_{j<=i} a_{t,s,j} - sum_{j<=i} a_{t,s',j}) >= q_p`
  variables: y_{t,k} (binary), a_{t,s,i} (binary), q_{p} (continuous)

## exp1.P1.glmflash.PS.t06.r15: 1 of 9 equations marked

- **Z**: `min w_1 sum_{t,s}(1-c_t)(a_{t,s}-a_t^0 + d_{t,s}-d_t^0) + w_2 sum_{t,i,k} e_{t,k} x_{t,i,k}`
  variables: a_{t,s} (continuous), d_{t,s} (continuous), c_t (binary), x_{t,i,k} (binary)

## exp1.P1.gptoss.ZS.t10.r14: 1 of 19 equations marked

- **T2**: `sum_{k} u_{t,s,k} * Delta = l_s / v_bar_{t,s}`
  variables: u_{t,s,k} (binary)

## exp2.P5.minimax.ZS.t06.r04: 1 of 17 equations marked

- **Reordering**: `y_{i,j,e} + y_{j,i,e} = z_{i,e} z_{j,e}`
  variables: y_{i,j,e} (binary), z_{i,e} (unknown)

## exp1.P1.qwen.ZS.t06.r11: 1 of 12 equations marked

- **Energy Approximation**: `E_{i,k} >= alpha * (RT_nom - RT_{i,k}) * (x_{i,k} + y_{i,k})`
  variables: x_{i,k} (binary), y_{i,k} (binary), RT_{i,k} (continuous), E_{i,k} (continuous)

## exp2.P5.gptoss.ZS.t06.r03: 1 of 12 equations marked

- **Node capacity**: `sum_{t in T} 1_{a^t_i <= theta < a^t_i + h_i} <= C^i`
  variables: a^t_i (continuous)

## exp2.P4.deepseek.ZS.t06.r15: 3 of 22 equations marked

- **Total Cost**: `min Z = c^{wait} \sum G_i + c^{travel} \sum E_i + c^{op} \sum n_c x_{i,c} \sum L_s + c^{dev} \sum (\delta_i^+ + \delta_i^-) + c^{comp} \sum u_{i,c,c'}`
  variables: G_i (continuous), E_i (continuous), x_{i,c} (binary), \delta_i^+ (continuous), \delta_i^- (continuous), u_{i,c,c'} (binary)
- **Waiting dynamics**: `W_{s,k} = W_{s,k-1} + \lambda_{s,k}^{arr} \Delta_k - \sum B_{i,s} 	heta_{i,s,k}`
  variables: W_{s,k} (continuous), B_{i,s} (continuous), 	heta_{i,s,k} (binary)
- **Boarding constraint**: `B_{i,s} \leq W_{s,k} 	heta_{i,s,k} + M(1 - 	heta_{i,s,k})`
  variables: B_{i,s} (continuous), W_{s,k} (continuous), 	heta_{i,s,k} (binary)

## exp2.P2.gptoss.ZS.t06.r12: 2 of 16 equations marked

- **Time-linking**: `x_{t,j} \ge y_{t,i} + L_{ij}/v_{t,i} - M(1-\beta_{t,(i,j)})`
  variables: x_{t,i} (continuous), y_{t,i} (continuous), \beta_{t,(i,j)} (binary)
- **Separation constraint**: `z_{t',d} \ge z_{t,d} + B^{brk}_{t}(v_{t,i^{out}(d)}) + \epsilon - M(1-\theta_{t,t',d})`
  variables: z_{t,d} (continuous), v_{t,i} (continuous), \theta_{t,t',d} (binary)

## exp1.P1.minimax.CFC.t02.r14: 2 of 21 equations marked

- **Departure timing**: `dep_i^s ≥ arr_i^s + dwell_i^s * z_i^s`
  variables: dep_i^s (continuous), arr_i^s (continuous), z_i^s (binary)
- **Position dynamics**: `p_i^{k,b+1} = p_i^{k,b} + v_i^{k,b}*δ_t + 0.5*a_i^{k,b}*δ_t^2`
  variables: p_i^{k,b} (continuous), v_i^{k,b} (continuous), a_i^{k,b} (continuous)

## exp1.P1.deepseek.CFC.t02.r05: 2 of 26 equations marked

- **Acceleration Limit**: `v_{k'} v_{i,p+1,k'} - v_k v_{i,p,k} \le a^{max} (L^{step}/v_k) + M(1 - v_{i,p,k})`
  variables: v_{i,p,k} (binary)
- **Deceleration Limit**: `v_k v_{i,p,k} - v_{k'} v_{i,p+1,k'} \le b^{max} (L^{step}/v_k) + M(1 - v_{i,p,k})`
  variables: v_{i,p,k} (binary)

## exp1.P1.deepseek.ZS.t10.r13: 2 of 14 equations marked

- **Speed-Position consistency**: `x_{i,k} >= X_s - M(1 - 1[k*Delta t <= a_{i,s}])`
  variables: a_{i,s} (continuous), x_{i,k} (continuous)
- **Acceleration bounds**: `|(v_{i,k+1} - v_{i,k})/Delta t| <= a^{max}`
  variables: v_{i,k} (continuous)

## exp1.P1.glmflash.ZS.t02.r09: 2 of 13 equations marked

- **Minimize total cost**: `∑ w_{is}[(a_{is}-a^{sched}_{is}) + (d_{is}-d^{sched}_{is})] + λ ∑ x_{ibp}(e_{ibp} + γ_{ibp}δ_{ibp}) + ∑ C_i z_i`
  variables: a_{is} (continuous), d_{is} (continuous), x_{ibp} (binary), z_i (binary), δ_{ibp} (continuous)
- **Running time consistency**: `d_{i,s} + ∑ (r_{ibp} + δ_{ibp})x_{ibp} = a_{i,s'}`
  variables: a_{is} (continuous), d_{is} (continuous), x_{ibp} (binary), δ_{ibp} (continuous)

## exp1.P1.minimax.OE.t06.r02: 1 of 33 equations marked

- **Position Dynamics**: `p_{i,k,t} = p_{i,k,t-1} + (delta_t/2)*(v_{i,k,t-1} + v_{i,k,t}) * x_{i,k,t}`
  variables: p_{i,k,t} (continuous), v_{i,k,t} (continuous), x_{i,k,t} (binary)

## exp1.P1.glmflash.PS.t06.r03: 1 of 19 equations marked

- **occupancy link 2**: `u_{i,s,t} \le 1 - c_i + (|a_{i,s}-t| + |d_{i,s}-t|)/M`
  variables: a_{i,s} (continuous), d_{i,s} (continuous), c_i (binary), u_{i,s,t} (binary)

## exp2.P3.deepseek.ZS.t06.r05: 1 of 19 equations marked

- **Coupling consistency**: `∑ x_{t,k} · ı[k 	ext{ can couple to } k'] ≥ x_{t',k'}`
  variables: x_{t,k} (binary)

## exp1.P1.deepseek.CFC.t06.r01: 1 of 11 equations marked

- **Energy_Def**: `e_t = ∑ (A + B v_{k,t} + C v_{max} v_{k,t}) v_{k,t} Δt`
  variables: e_t (continuous), v_{k,t} (continuous)

## exp1.P1.minimax.PS.t02.r02: 1 of 19 equations marked

- **Energy Constraints**: `f_{t,i,k} <= P_{max}/(v_{t,i,k}+eps) (and others)`
  variables: v_{t,i,k} (continuous), e_{t,i,k} (continuous), f_{t,i,k} (continuous)

## exp1.P1.gptoss.ZS.t02.r09: 1 of 14 equations marked

- **Position index sum**: `\sum p \cdot q_{tep} = \sum p_{tek} \cdot ho_{ek}`
  variables: p_{tek} (binary), q_{tep} (binary)

## exp1.P1.qwen.CFC.t10.r10: 1 of 15 equations marked

- **Total cost**: `min w_delay * sum|a_t(s) - a^{pl}_t(s)| + w_energy * sum E_{t,b} + w_route * sum R_t`
  variables: a_t(s) (continuous), d_t(s) (continuous), E_{t,b} (continuous), R_t (binary), y_t(s) (continuous)

## exp1.P1.minimax.CFC.t06.r08: 1 of 25 equations marked

- **Kinematics Running Time**: `f_t^b = L_b / v_t^b`
  variables: f_t^b (continuous), v_t^b (continuous)

## exp1.P1.minimax.ZS.t02.r11: 3 of 29 equations marked

- **Platform presence link 1**: `p_{t,s,k} ≥ α_{t,s} - kΔt - M(1 - p_{t,s,k})`
  variables: α_{t,s} (continuous), p_{t,s,k} (binary)
- **Platform presence link 2**: `p_{t,s,k} ≥ kΔt - β_{t,s} - M(1 - p_{t,s,k})`
  variables: β_{t,s} (continuous), p_{t,s,k} (binary)
- **Energy model**: `e_{t,b,k} = η^{tract} m_t a_{t,b,k}^{+} v_{t,b,k} + η^{cruise} v_{t,b,k} + η^{brake} m_t a_{t,b,k}^{-} v_{t,b,k}`
  variables: v_{t,b,k} (continuous), a_{t,b,k} (continuous), e_{t,b,k} (continuous), a_{t,b,k}^{±} (continuous), u_{t,b,k}^{\pm} (continuous)

## exp1.P1.minimax.ZS.t06.r02: 3 of 27 equations marked

- **Minimize total cost**: `min Z = c^{delay} sum delta_{i,j} + c^{cancel} sum c_i + c^{energy} sum e^{net}_{i,k} + c^{dev} sum |arr_{i,j} - T^{sch}_{i,j}|`
  variables: delta_{i,j} (continuous), c_i (binary), e^{net}_{i,k} (continuous), arr_{i,j} (continuous)
- **Energy consumption**: `e_{i,k} = \alpha M_i v_{i,k} + eta M_i a^{+}_{i,k} v_{i,k} + \gamma`
  variables: v_{i,k} (continuous), a_{i,k} (continuous), e_{i,k} (continuous)
- **Regenerative energy**: `e^{reg}_{i,k} = \eta M_i |a_{i,k}| v_{i,k} p^{brake}_{i,k}`
  variables: v_{i,k} (continuous), a_{i,k} (continuous), e^{reg}_{i,k} (continuous), p^{brake}_{i,k} (binary)

## exp1.P1.minimax.ZS.t10.r08: 2 of 16 equations marked

- **OBJ**: `min w_1\sum\delta_{t,s} + w_2 \Delta t \sum e_{t,b,k} + w_3 \sum P^c_t (1-c_t)`
  variables: \delta_{t,s} (continuous), e_{t,b,k} (continuous), c_t (binary)
- **C4b**: `\sum v_{t,b,k}(x_{t,b,k}+\tilde{x}_{t,b,k}) \le \sum \lambda_{t,b,v} v \underline{\tau}_{t,b}(v) + M(1-c_t)`
  variables: v_{t,b,k} (continuous), x_{t,b,k} (binary), \tilde{x}_{t,b,k} (binary), \lambda_{t,b,v} (continuous), c_t (binary)

## exp1.P1.deepseek.ZS.t10.r05: 1 of 15 equations marked

- **Fixed trains**: `|d_{i,0}-T^{dep}_i| ≤ ε`
  variables: d_{i,j} (continuous)

## exp1.P1.minimax.PS.t10.r09: 4 of 42 equations marked

- **Z**: `min Z = W_dly*sum(a+) + W_dly*sum(d+) + W_eng*sum(e) + W_cxl*sum(Pc*cxl)`
  variables: cxl (binary), a (continuous), d (continuous), e (continuous)
- **C7c**: `y_stn[t1,t2,s] + y_stn[t2,t1,s] = x[t1,s]*x[t2,s]`
  variables: x (binary), y_stn (binary)
- **C8b**: `z[t1,b,k] + z[t2,b,k] <= 1 + sum(M*(1 - r1*r2))`
  variables: r (binary), z (binary)
- **C10c**: `y_blk[t1,t2,b] + y_blk[t2,t1,b] = sum(r1*r2)`
  variables: r (binary), y_blk (binary)

## exp1.P1.glmflash.CFC.t06.r03: 1 of 11 equations marked

- **Occupation linking**: `y_{t,s*,b} ≥ 1 - (b + |b| - A_{t,s*})/M; y_{t,s*,b} ≥ 1 - (D_{t,s*} - b)/M; y_{t,s*,b} ≤ (D_{t,s*} - b)/M + (b + |b| - A_{t,s*})/M`
  variables: A_{t,s} (continuous), D_{t,s} (continuous), y_{t,s,b} (binary)

## exp2.P5.minimax.ZS.t06.r06: 1 of 20 equations marked

- **Route-conflict link**: `y_{i,j} <= sum(sum(beta_{i,r,k} * beta_{j,r',k} * z_{i,r} * z_{j,r'}))`
  variables: y_{i,j} (binary), z_{i,r} (binary)

## exp2.P4.qwen.ZS.t06.r13: 2 of 12 equations marked

- **Z**: `sum_{a,i} w_{wait} W_{a,i} + sum_{k,a} w_{travel} L_{k,a} t_{run}(a) + sum_{k,c} w_{cost} c x_{k,c}`
  variables: x_{k,c} (binary), y_{k,a,i} (binary), t_{k,s} (continuous), L_{k,a} (continuous), W_{a,i} (continuous)
- **Passenger Flow**: `W_{a,i} = D_{a,i} - sum_{k} L_{k,a} y_{k,a,i}`
  variables: y_{k,a,i} (binary), L_{k,a} (continuous), W_{a,i} (continuous)

## exp1.P1.minimax.OE.t06.r08: 1 of 20 equations marked

- **Position Update**: `s_{t,b,k} = s_{t,b,k-1} + v_{t,b,k-1}*Delta + 0.5*(A*u - B*q)*Delta^2`
  variables: s_{t,b,k} (continuous), v_{t,b,k} (continuous), u_{t,b,k} (binary), q_{t,b,k} (binary)

## exp2.P3.glmflash.ZS.t06.r06: 1 of 7 equations marked

- **Rolling Stock Cost**: `∑ w^{canc} y_t + w^{delay} d_t + w^{car} ∑ c_k x_{t,k} + w^{shunt} ∑ s_{a,k} + w^{dev} ∑ |x_{t,k} - āx_{t,k}|`
  variables: x_{t,k} (integer), y_{t} (binary), d_t (integer), s_{a,k} (integer)

## exp1.P1.gptoss.CFC.t06.r04: 1 of 9 equations marked

- **min delay and energy**: `w^{delay} \sum (a_{i,last}-schedArr_i) + w^{energy} \sum \sum \alpha_s v_{i,s}^2 t_{i,s}`
  variables: a_{i,k} (continuous), v_{i,s} (continuous), t_{i,s} (continuous)

## exp1.P1.minimax.OE.t10.r09: 1 of 42 equations marked

- **Energy calculation**: `e_{i,b,k} = (E_a*acc_{i,b,k} + E_c*cru_{i,b,k}*v_{i,b,k}/3600 + E_d*dec_{i,b,k})*Delta t`
  variables: e_{i,b,k} (continuous), acc_{i,b,k} (binary), cru_{i,b,k} (binary), v_{i,b,k} (continuous), dec_{i,b,k} (binary)

## exp1.P1.deepseek.CFC.t10.r11: 1 of 13 equations marked

- **C9 Accel/Braking**: `u_{p+1} - u_p <= a_max(tpos_{p+1}-tpos_p)`
  variables: u_{i,seg,p} (continuous), tpos_{i,seg,p} (continuous)

## exp1.P1.minimax.ZS.t10.r03: 3 of 28 equations marked

- **Total weighted operating cost**: `min Z = Z_delay + Z_dwell + Z_energy + Z_cancel + Z_reroute + Z_conflict`
  variables: u_t (binary), d_{t,i} (continuous), c_{t,i} (continuous), E_t (continuous), y_{t,ij}^d (binary), r_{t,ij}^d (binary), w_{t,h}^{ij} (binary)
- **Velocity update**: `v_{t,h+1} = v_{t,h} + (dt/m)f_{t,h} - dt*Res(v_{t,h})`
  variables: v_{t,h} (continuous), f_{t,h} (continuous)
- **Power consumption**: `e_{t,h} >= eta^-1 * f_{t,h} * v_{t,h}`
  variables: f_{t,h} (continuous), v_{t,h} (continuous), e_{t,h} (continuous)

## exp1.P1.minimax.ZS.t06.r15: 1 of 19 equations marked

- **Minimize weighted delay, energy and cancellation**: `\min \alpha \sum dly_{t,s} + \beta \sum e_{t,b,k} + \gamma \sum w_t C^{cancel}_t`
  variables: w_t (binary), dly_{t,s} (continuous), e_{t,b,k} (continuous)

## exp2.P3.gptoss.ZS.t06.r06: 2 of 14 equations marked

- **Shunting Track Occupancy**: `u_{nkp} >= z_s if p in [\tau_s, \tau_s+L_s]`
  variables: z_s (binary), u_{nkp} (binary), \tau_s (continuous)
- **Track Capacity**: `sum 1_{p in [d_t+d_t, a_t+a_t]} + sum u_{nkp} <= C^{track}_{nk}`
  variables: d_t^{+} (continuous), u_{nkp} (binary)

## exp1.P1.qwen.ZS.t10.r05: 1 of 10 equations marked

- **Link Connectivity**: `Arr_{t,s'} \geq Dep_{t,s} + \sum x_{t,r} Run_{t,l(r),r}`
  variables: x_{t,r} (binary), Dep_{t,s} (continuous), Run_{t,l,r} (continuous)
