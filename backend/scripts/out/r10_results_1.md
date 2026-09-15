# R10 paid smoke trial

Model: `deepseek-v4-pro-0813` via DashScope. Room: 40. Seed: 1.

Completed calls: 600/600. Parsed answers: 598. Errors: 0.
Provider-reported tokens: {'completion_tokens': 33827, 'prompt_tokens': 575145, 'total_tokens': 608972}. Listed-rate upper estimate for reported usage: US$0.8931; not an invoice.
Responses without usage: 0. Weighted effective sample size: 29.8.

Distribution gap is total variation distance in percentage points. Lower is closer. No overall validation score.

| Item | Group | Parsed | Raw gap (pp) | Weighted gap (pp) |
|---|---|---:|---:|---:|
| Q38E_Q38E | held_out | 40/40 | 45.50 | 39.50 |
| Q38F_Q38F | held_out | 40/40 | 64.10 | 65.97 |
| Q38G_Q38G | held_out | 40/40 | 38.50 | 40.42 |
| Q37F_Q37F | held_out | 40/40 | 39.13 | 37.83 |
| Q37I_Q37I | held_out | 40/40 | 37.00 | 35.62 |
| Q37B_Q37B | held_out | 39/40 | 12.38 | 14.07 |
| Q46E_Q47E | held_out | 39/40 | 29.45 | 30.17 |
| Q46B_Q47B | held_out | 40/40 | 39.08 | 35.18 |
| Q9A_Q10A | held_out | 40/40 | 58.90 | 58.90 |
| Q5A_Q5A | held_out | 40/40 | 60.80 | 62.68 |
| Q47A_Q48A | held_out | 40/40 | 55.20 | 53.54 |
| Q37G_Q37G | held_out | 40/40 | 43.13 | 43.57 |
| Q37A_Q37A | seen | 40/40 | 22.30 | 25.12 |
| Q4A_Q4A | seen | 40/40 | 26.33 | 26.33 |
| Q46F_Q47F | seen | 40/40 | 51.20 | 54.50 |

## Held-out and control summaries

```json
{
  "held_out": {
    "unweighted": {
      "scorable_items": 12,
      "mean_tvd_pp": 43.597929139595806,
      "median_tvd_pp": 41.13136863136863,
      "urban_rural_focus_sign_correct": 5,
      "urban_rural_focus_scorable": 12
    },
    "weighted": {
      "scorable_items": 12,
      "mean_tvd_pp": 43.12175130470178,
      "median_tvd_pp": 39.960909287603144,
      "urban_rural_focus_sign_correct": 4,
      "urban_rural_focus_scorable": 12
    }
  },
  "seen": {
    "unweighted": {
      "scorable_items": 3,
      "mean_tvd_pp": 33.275442108775444,
      "median_tvd_pp": 26.326326326326328,
      "urban_rural_focus_sign_correct": 0,
      "urban_rural_focus_scorable": 3
    },
    "weighted": {
      "scorable_items": 3,
      "mean_tvd_pp": 35.31514424083069,
      "median_tvd_pp": 26.326326326326328,
      "urban_rural_focus_sign_correct": 0,
      "urban_rural_focus_scorable": 3
    }
  }
}
```

## Primary subgroup gaps

Positive means Urban exceeds Rural, or Men exceeds Women. These use the frozen focus answer, not a result-picked option.

| Item | Comparison | Focus answer | Raw predicted | Weighted predicted | Real | Raw sign correct |
|---|---|---|---:|---:|---:|---|
| Q38E_Q38E | location | All of them | 0.00 | 0.00 | 5.90 | False |
| Q38E_Q38E | gender | All of them | 0.00 | 0.00 | -10.40 | False |
| Q38F_Q38F | location | All of them | 0.00 | 0.00 | 6.00 | False |
| Q38F_Q38F | gender | All of them | 0.00 | 0.00 | -8.70 | False |
| Q38G_Q38G | location | Most of them | 8.52 | 4.67 | 4.80 | True |
| Q38G_Q38G | gender | Most of them | 15.86 | 11.53 | 2.30 | True |
| Q37F_Q37F | location | Not at all | -37.84 | -45.72 | 4.20 | False |
| Q37F_Q37F | gender | Not at all | -3.32 | -10.85 | -6.20 | True |
| Q37I_Q37I | location | Just a little | -6.52 | -5.23 | 3.20 | False |
| Q37I_Q37I | gender | Just a little | 0.51 | -7.14 | -1.80 | False |
| Q37B_Q37B | location | A lot | 0.00 | 0.00 | -3.50 | False |
| Q37B_Q37B | gender | A lot | 0.00 | 0.00 | -1.50 | False |
| Q46E_Q47E | location | Fairly badly | 13.49 | 27.87 | 1.90 | True |
| Q46E_Q47E | gender | Fairly badly | -12.03 | -9.16 | 0.70 | False |
| Q46B_Q47B | location | Fairly badly | 24.06 | 36.44 | 6.30 | True |
| Q46B_Q47B | gender | Fairly badly | 2.05 | -2.84 | -2.80 | False |
| Q9A_Q10A | location | Somewhat free | 4.01 | 17.29 | 1.80 | True |
| Q9A_Q10A | gender | Somewhat free | 2.05 | -1.62 | -2.40 | False |
| Q5A_Q5A | location | Much worse | -5.76 | -3.74 | 4.60 | False |
| Q5A_Q5A | gender | Much worse | 2.81 | 2.46 | 0.30 | True |
| Q47A_Q48A | location | Strongly approve | 0.00 | 0.00 | 5.00 | False |
| Q47A_Q48A | gender | Strongly approve | 0.00 | 0.00 | -4.80 | False |
| Q37G_Q37G | location | Somewhat | -0.50 | 1.54 | -3.30 | True |
| Q37G_Q37G | gender | Somewhat | -1.53 | 2.01 | 2.20 | False |
| Q37A_Q37A | location | A lot | 0.00 | 0.00 | 3.70 | False |
| Q37A_Q37A | gender | A lot | 0.00 | 0.00 | -2.20 | False |
| Q4A_Q4A | location | Very bad | -11.28 | -28.79 | 2.40 | False |
| Q4A_Q4A | gender | Very bad | 16.62 | 11.30 | -6.50 | False |
| Q46F_Q47F | location | Very badly | -3.51 | -2.45 | 15.20 | False |
| Q46F_Q47F | gender | Very badly | 9.72 | -1.47 | -3.30 | False |

## Spread and full answer distributions

The JSON report includes every subgroup option, raw counts, weighted counts and spread measures.

### Q38E_Q38E

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Police?

Spread, unweighted: `{"tvd_pp": 45.49999999999999, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.5, "tail_gap_pp": -21.5, "modal_ours_pct": 72.5, "modal_real_pct": 48.9, "modal_excess_pp": 23.6, "pass": false}`
Spread, weighted: `{"tvd_pp": 39.497891772585334, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.5, "tail_gap_pp": -21.5, "modal_ours_pct": 66.49789177258533, "modal_real_pct": 48.9, "modal_excess_pp": 17.597891772585335, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 2.00 |
| Some of them | 29 | 66.50 | 27.00 |
| Most of them | 11 | 33.50 | 48.90 |
| All of them | 0 | 0.00 | 19.50 |
| Refused | 0 | 0.00 | 1.70 |
| Don't know/Haven't heard | 0 | 0.00 | 0.90 |

### Q38F_Q38F

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Judges and magistrates?

Spread, unweighted: `{"tvd_pp": 64.1, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 17.299999999999997, "tail_gap_pp": -17.299999999999997, "modal_ours_pct": 67.5, "modal_real_pct": 45.6, "modal_excess_pp": 21.9, "pass": false}`
Spread, weighted: `{"tvd_pp": 65.97411783323581, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 17.299999999999997, "tail_gap_pp": -17.299999999999997, "modal_ours_pct": 69.37411783323581, "modal_real_pct": 45.6, "modal_excess_pp": 23.774117833235813, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 4.60 |
| Some of them | 13 | 30.63 | 45.60 |
| Most of them | 0 | 0.00 | 33.70 |
| All of them | 0 | 0.00 | 12.70 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard | 27 | 69.37 | 3.40 |

### Q38G_Q38G

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Tax officials, like officials from the South African Revenue Service or SARS?

Spread, unweighted: `{"tvd_pp": 38.5, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.9, "tail_gap_pp": -21.9, "modal_ours_pct": 60.0, "modal_real_pct": 36.8, "modal_excess_pp": 23.200000000000003, "pass": false}`
Spread, weighted: `{"tvd_pp": 40.42392680262096, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.9, "tail_gap_pp": -21.9, "modal_ours_pct": 62.39365488301717, "modal_real_pct": 36.8, "modal_excess_pp": 25.593654883017173, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 5.80 |
| Some of them | 24 | 62.39 | 36.80 |
| Most of them | 6 | 13.08 | 31.60 |
| All of them | 0 | 0.00 | 16.10 |
| Don't know/Haven't heard | 10 | 24.53 | 9.70 |

### Q37F_Q37F

How much do you trust each of the following, or haven't you heard enough about them to say: Opposition political parties?

Spread, unweighted: `{"tvd_pp": 39.133366633366634, "tail_mass_ours_pct": 27.500000000000004, "tail_mass_real_pct": 43.25674325674326, "tail_gap_pp": -15.75674325674326, "modal_ours_pct": 62.5, "modal_real_pct": 36.56343656343657, "modal_excess_pp": 25.936563436563432, "pass": false}`
Spread, weighted: `{"tvd_pp": 37.82550360828655, "tail_mass_ours_pct": 28.80786302508008, "tail_mass_real_pct": 43.25674325674326, "tail_gap_pp": -14.448880231663182, "modal_ours_pct": 65.21433755873709, "modal_real_pct": 36.56343656343657, "modal_excess_pp": 28.650900995300518, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 11 | 28.81 | 36.56 |
| Just a little | 25 | 65.21 | 32.37 |
| Somewhat | 0 | 0.00 | 23.38 |
| A lot | 0 | 0.00 | 6.69 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 4 | 5.98 | 1.00 |

### Q37I_Q37I

How much do you trust each of the following, or haven't you heard enough about them to say: Courts of law?

Spread, unweighted: `{"tvd_pp": 37.00000000000001, "tail_mass_ours_pct": 10.0, "tail_mass_real_pct": 36.9, "tail_gap_pp": -26.9, "modal_ours_pct": 65.0, "modal_real_pct": 33.8, "modal_excess_pp": 31.200000000000003, "pass": false}`
Spread, weighted: `{"tvd_pp": 35.61911838657047, "tail_mass_ours_pct": 9.948605948608227, "tail_mass_real_pct": 36.9, "tail_gap_pp": -26.951394051391773, "modal_ours_pct": 65.87091376041262, "modal_real_pct": 33.8, "modal_excess_pp": 32.07091376041262, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 4 | 9.95 | 21.10 |
| Just a little | 26 | 65.87 | 33.80 |
| Somewhat | 7 | 18.93 | 27.60 |
| A lot | 0 | 0.00 | 15.80 |
| Don't know/Haven't heard enough to say | 3 | 5.25 | 1.70 |

### Q37B_Q37B

How much do you trust each of the following, or haven't you heard enough about them to say: Parliament?

Spread, unweighted: `{"tvd_pp": 12.37948717948718, "tail_mass_ours_pct": 43.58974358974359, "tail_mass_real_pct": 44.2, "tail_gap_pp": -0.6102564102564116, "modal_ours_pct": 43.58974358974359, "modal_real_pct": 39.2, "modal_excess_pp": 4.389743589743588, "pass": true}`
Spread, weighted: `{"tvd_pp": 14.074805400102047, "tail_mass_ours_pct": 44.516702980456046, "tail_mass_real_pct": 44.2, "tail_gap_pp": 0.31670298045604284, "modal_ours_pct": 44.516702980456046, "modal_real_pct": 39.2, "modal_excess_pp": 5.316702980456043, "pass": true}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 17 | 44.52 | 39.20 |
| Just a little | 16 | 43.02 | 34.50 |
| Somewhat | 5 | 11.13 | 20.20 |
| A lot | 0 | 0.00 | 5.00 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 1 | 1.34 | 1.10 |

### Q46E_Q47E

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Narrowing gaps between rich and poor?

Spread, unweighted: `{"tvd_pp": 29.453846153846158, "tail_mass_ours_pct": 53.84615384615385, "tail_mass_real_pct": 76.9, "tail_gap_pp": -23.05384615384616, "modal_ours_pct": 53.84615384615385, "modal_real_pct": 76.4, "modal_excess_pp": -22.55384615384616, "pass": false}`
Spread, weighted: `{"tvd_pp": 30.174912966703076, "tail_mass_ours_pct": 53.12508703329692, "tail_mass_real_pct": 76.9, "tail_gap_pp": -23.774912966703084, "modal_ours_pct": 53.12508703329692, "modal_real_pct": 76.4, "modal_excess_pp": -23.274912966703084, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 21 | 53.13 | 76.40 |
| Fairly badly | 18 | 46.87 | 16.70 |
| Fairly well | 0 | 0.00 | 4.90 |
| Very well | 0 | 0.00 | 0.50 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 1.50 |

### Q46B_Q47B

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Improving the living standards of the poor?

Spread, unweighted: `{"tvd_pp": 39.07907907907908, "tail_mass_ours_pct": 37.5, "tail_mass_real_pct": 71.07107107107107, "tail_gap_pp": -33.571071071071074, "modal_ours_pct": 60.0, "modal_real_pct": 69.96996996996997, "modal_excess_pp": -9.969969969969966, "pass": false}`
Spread, weighted: `{"tvd_pp": 35.18140696939543, "tail_mass_ours_pct": 43.89767210968365, "tail_mass_real_pct": 71.07107107107107, "tail_gap_pp": -27.173398961387427, "modal_ours_pct": 56.10232789031636, "modal_real_pct": 69.96996996996997, "modal_excess_pp": -13.867642079653606, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 15 | 43.90 | 69.97 |
| Fairly badly | 24 | 56.10 | 20.92 |
| Fairly well | 1 | 0.00 | 7.51 |
| Very well | 0 | 0.00 | 1.10 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.50 |

### Q9A_Q10A

In this country, how free are you to say what you think?

Spread, unweighted: `{"tvd_pp": 58.9, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 58.099999999999994, "tail_gap_pp": -58.099999999999994, "modal_ours_pct": 60.0, "modal_real_pct": 43.1, "modal_excess_pp": 16.9, "pass": false}`
Spread, weighted: `{"tvd_pp": 58.900000000000006, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 58.099999999999994, "tail_gap_pp": -58.099999999999994, "modal_ours_pct": 57.37949599806832, "modal_real_pct": 43.1, "modal_excess_pp": 14.27949599806832, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all free | 0 | 0.00 | 15.00 |
| Not very free | 16 | 42.62 | 18.00 |
| Somewhat free | 24 | 57.38 | 23.10 |
| Completely free | 0 | 0.00 | 43.10 |
| Refused | 0 | 0.00 | 0.40 |
| Don't know | 0 | 0.00 | 0.40 |

### Q5A_Q5A

Looking back, how do you rate the following compared to 12 months ago: Economic condition of this country?

Spread, unweighted: `{"tvd_pp": 60.8, "tail_mass_ours_pct": 7.5, "tail_mass_real_pct": 35.300000000000004, "tail_gap_pp": -27.800000000000004, "modal_ours_pct": 87.5, "modal_real_pct": 34.2, "modal_excess_pp": 53.3, "pass": false}`
Spread, weighted: `{"tvd_pp": 62.67796104052729, "tail_mass_ours_pct": 6.750114298435932, "tail_mass_real_pct": 35.300000000000004, "tail_gap_pp": -28.549885701564072, "modal_ours_pct": 89.37796104052728, "modal_real_pct": 34.2, "modal_excess_pp": 55.17796104052728, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Much worse | 3 | 6.75 | 34.20 |
| Worse | 35 | 89.38 | 26.70 |
| Same | 1 | 2.25 | 28.80 |
| Better | 1 | 1.62 | 9.10 |
| Much better | 0 | 0.00 | 1.10 |
| Don't know | 0 | 0.00 | 0.10 |

### Q47A_Q48A

Do you approve or disapprove of the way that the following people have performed their jobs over the past 12 months, or haven't you heard enough about them to say: President Cyril Ramaphosa?

Spread, unweighted: `{"tvd_pp": 55.2, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 41.699999999999996, "tail_gap_pp": -41.699999999999996, "modal_ours_pct": 85.0, "modal_real_pct": 33.8, "modal_excess_pp": 51.2, "pass": false}`
Spread, weighted: `{"tvd_pp": 53.54271047687408, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 41.699999999999996, "tail_gap_pp": -41.699999999999996, "modal_ours_pct": 83.53184992709222, "modal_real_pct": 33.8, "modal_excess_pp": 49.73184992709223, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Strongly disapprove | 0 | 0.00 | 33.80 |
| Disapprove | 34 | 83.53 | 32.30 |
| Approve | 4 | 11.66 | 23.30 |
| Strongly approve | 0 | 0.00 | 7.90 |
| Refused | 0 | 0.00 | 0.20 |
| Don't know or haven't heard enough to say | 2 | 4.81 | 2.50 |

### Q37G_Q37G

How much do you trust each of the following, or haven't you heard enough about them to say: The police?

Spread, unweighted: `{"tvd_pp": 43.129370629370634, "tail_mass_ours_pct": 22.5, "tail_mass_real_pct": 52.54745254745256, "tail_gap_pp": -30.047452547452558, "modal_ours_pct": 72.5, "modal_real_pct": 40.55944055944056, "modal_excess_pp": 31.94055944055944, "pass": false}`
Spread, weighted: `{"tvd_pp": 43.56866039952029, "tail_mass_ours_pct": 18.05724821999032, "tail_mass_real_pct": 52.54745254745256, "tail_gap_pp": -34.49020432746224, "modal_ours_pct": 72.93928977014966, "modal_real_pct": 40.55944055944056, "modal_excess_pp": 32.3798492107091, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 9 | 18.06 | 40.56 |
| Just a little | 29 | 72.94 | 29.37 |
| Somewhat | 2 | 9.00 | 17.68 |
| A lot | 0 | 0.00 | 11.99 |
| Refused | 0 | 0.00 | 0.10 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.30 |

### Q37A_Q37A

How much do you trust each of the following, or haven't you heard enough about them to say: The president?

Spread, unweighted: `{"tvd_pp": 22.3, "tail_mass_ours_pct": 55.00000000000001, "tail_mass_real_pct": 49.8, "tail_gap_pp": 5.20000000000001, "modal_ours_pct": 55.00000000000001, "modal_real_pct": 39.5, "modal_excess_pp": 15.500000000000007, "pass": false}`
Spread, weighted: `{"tvd_pp": 25.119039479718214, "tail_mass_ours_pct": 59.95256674171965, "tail_mass_real_pct": 49.8, "tail_gap_pp": 10.152566741719653, "modal_ours_pct": 59.95256674171965, "modal_real_pct": 39.5, "modal_excess_pp": 20.45256674171965, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 22 | 59.95 | 39.50 |
| Just a little | 15 | 35.37 | 30.70 |
| Somewhat | 3 | 4.68 | 18.90 |
| A lot | 0 | 0.00 | 10.30 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.60 |

### Q4A_Q4A

In general, how would you describe the present economic condition of this country?

Spread, unweighted: `{"tvd_pp": 26.326326326326328, "tail_mass_ours_pct": 62.5, "tail_mass_real_pct": 58.05805805805806, "tail_gap_pp": 4.441941941941941, "modal_ours_pct": 62.5, "modal_real_pct": 51.85185185185185, "modal_excess_pp": 10.648148148148152, "pass": true}`
Spread, weighted: `{"tvd_pp": 26.326326326326328, "tail_mass_ours_pct": 60.10348743363368, "tail_mass_real_pct": 58.05805805805806, "tail_gap_pp": 2.0454293755756225, "modal_ours_pct": 60.10348743363368, "modal_real_pct": 51.85185185185185, "modal_excess_pp": 8.251635581781834, "pass": true}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very bad | 25 | 60.10 | 51.85 |
| Fairly bad | 15 | 39.90 | 21.82 |
| Neither good nor bad | 0 | 0.00 | 6.31 |
| Fairly good | 0 | 0.00 | 12.71 |
| Very good | 0 | 0.00 | 6.21 |
| Refused | 0 | 0.00 | 0.10 |
| Don't know | 0 | 0.00 | 1.00 |

### Q46F_Q47F

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Reducing crime?

Spread, unweighted: `{"tvd_pp": 51.2, "tail_mass_ours_pct": 35.0, "tail_mass_real_pct": 82.0, "tail_gap_pp": -47.0, "modal_ours_pct": 62.5, "modal_real_pct": 79.8, "modal_excess_pp": -17.299999999999997, "pass": false}`
Spread, weighted: `{"tvd_pp": 54.50006691644753, "tail_mass_ours_pct": 32.11419985739059, "tail_mass_real_pct": 82.0, "tail_gap_pp": -49.88580014260941, "modal_ours_pct": 65.80006691644755, "modal_real_pct": 79.8, "modal_excess_pp": -13.999933083552449, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 14 | 32.11 | 79.80 |
| Fairly badly | 25 | 65.80 | 11.30 |
| Fairly well | 1 | 2.09 | 6.50 |
| Very well | 0 | 0.00 | 2.20 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.20 |

## Limitations

- 40-person single-seed smoke, not population accuracy proof
- Full-library weights do not make the 40-person sample representative
- Held-out from fused survey fields, not guaranteed absent from model training or narrative prose
- Narrative prose retained without semantic validation; deterministic belief sentences checked
- Local repaired library loaded fresh; deployed service not tested
- Missing R10 cells are not zero. Incomplete national tables are not scored.
- Missing model answers are excluded from shares and counted separately; this may bias the result.
- Published percentages are rounded. Full known national rows are normalized to sum to one.
- Weighting exclusions and unsupported target categories are recorded in the JSON; weighted results cover supported groups only.
- Previous identical-people diagnostic remains 15/15 directions, one health-service warning; this trial does not erase it.

## Blind record

Manifest SHA256: `c8b0436594630708ce19378335089f104753793011365094cfcf9a15f93304c5`
Saved run SHA256: `ff419ec53aaf59b774b31f709f09d545d282dba96ca09109116d6500aeea5423`
Raw answers and prompts stay local. Ask wrote the receipt before reveal loaded the frozen outcome file.
