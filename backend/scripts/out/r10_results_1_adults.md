# R10 paid smoke trial

Model: `deepseek-v4-pro-0813` via DashScope. Room: 32. Seed: 1.

Original run calls: 600/600. Original parsed answers: 598. Errors: 0.
Analysis: Post-hoc adult-only sensitivity. Included replies: 480; parsed: 478.
Provider-reported tokens: {'completion_tokens': 33827, 'prompt_tokens': 575145, 'total_tokens': 608972}. Listed-rate upper estimate for reported usage: US$0.8931; not an invoice.
Responses without usage: 0. Weighted effective sample size: 24.8.

Distribution gap is total variation distance in percentage points. Lower is closer. No overall validation score.

| Item | Group | Parsed | Raw gap (pp) | Weighted gap (pp) |
|---|---|---:|---:|---:|
| Q38E_Q38E | held_out | 32/32 | 44.88 | 36.75 |
| Q38F_Q38F | held_out | 32/32 | 62.22 | 65.08 |
| Q38G_Q38G | held_out | 32/32 | 37.88 | 40.44 |
| Q37F_Q37F | held_out | 32/32 | 35.38 | 33.97 |
| Q37I_Q37I | held_out | 32/32 | 39.50 | 37.23 |
| Q37B_Q37B | held_out | 31/32 | 16.62 | 19.22 |
| Q46E_Q47E | held_out | 31/32 | 25.24 | 25.99 |
| Q46B_Q47B | held_out | 32/32 | 32.20 | 29.44 |
| Q9A_Q10A | held_out | 32/32 | 58.90 | 58.90 |
| Q5A_Q5A | held_out | 32/32 | 60.80 | 60.15 |
| Q47A_Q48A | held_out | 32/32 | 55.83 | 55.73 |
| Q37G_Q37G | held_out | 32/32 | 45.63 | 42.11 |
| Q37A_Q37A | seen | 32/32 | 26.67 | 29.80 |
| Q4A_Q4A | seen | 32/32 | 26.33 | 26.33 |
| Q46F_Q47F | seen | 32/32 | 48.07 | 50.64 |

## Held-out and control summaries

```json
{
  "held_out": {
    "unweighted": {
      "scorable_items": 12,
      "mean_tvd_pp": 42.92290673816211,
      "median_tvd_pp": 42.1875,
      "urban_rural_focus_sign_correct": 6,
      "urban_rural_focus_scorable": 12
    },
    "weighted": {
      "scorable_items": 12,
      "mean_tvd_pp": 42.083659365099344,
      "median_tvd_pp": 38.83236966308904,
      "urban_rural_focus_sign_correct": 6,
      "urban_rural_focus_scorable": 12
    }
  },
  "seen": {
    "unweighted": {
      "scorable_items": 3,
      "mean_tvd_pp": 33.69210877544211,
      "median_tvd_pp": 26.674999999999997,
      "urban_rural_focus_sign_correct": 1,
      "urban_rural_focus_scorable": 3
    },
    "weighted": {
      "scorable_items": 3,
      "mean_tvd_pp": 35.587617871544886,
      "median_tvd_pp": 29.800000000000004,
      "urban_rural_focus_sign_correct": 1,
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
| Q38G_Q38G | location | Most of them | 10.32 | 4.77 | 4.80 | True |
| Q38G_Q38G | gender | Most of them | 16.86 | 11.81 | 2.30 | True |
| Q37F_Q37F | location | Not at all | -42.86 | -52.78 | 4.20 | False |
| Q37F_Q37F | gender | Not at all | -3.92 | -15.21 | -6.20 | True |
| Q37I_Q37I | location | Just a little | 11.90 | 16.13 | 3.20 | True |
| Q37I_Q37I | gender | Just a little | -2.75 | -2.51 | -1.80 | True |
| Q37B_Q37B | location | A lot | 0.00 | 0.00 | -3.50 | False |
| Q37B_Q37B | gender | A lot | 0.00 | 0.00 | -1.50 | False |
| Q46E_Q47E | location | Fairly badly | 1.68 | 21.85 | 1.90 | True |
| Q46E_Q47E | gender | Fairly badly | -9.17 | -3.06 | 0.70 | False |
| Q46B_Q47B | location | Fairly badly | 19.84 | 32.65 | 6.30 | True |
| Q46B_Q47B | gender | Fairly badly | -0.39 | -0.00 | -2.80 | True |
| Q9A_Q10A | location | Somewhat free | 1.59 | 16.41 | 1.80 | True |
| Q9A_Q10A | gender | Somewhat free | 5.49 | 6.04 | -2.40 | False |
| Q5A_Q5A | location | Much worse | 1.59 | 0.53 | 4.60 | True |
| Q5A_Q5A | gender | Much worse | -0.78 | -0.66 | 0.30 | False |
| Q47A_Q48A | location | Strongly approve | 0.00 | 0.00 | 5.00 | False |
| Q47A_Q48A | gender | Strongly approve | 0.00 | 0.00 | -4.80 | False |
| Q37G_Q37G | location | Somewhat | 1.59 | 3.30 | -3.30 | False |
| Q37G_Q37G | gender | Somewhat | -0.78 | 1.48 | 2.20 | False |
| Q37A_Q37A | location | A lot | 0.00 | 0.00 | 3.70 | False |
| Q37A_Q37A | gender | A lot | 0.00 | 0.00 | -2.20 | False |
| Q4A_Q4A | location | Very bad | -16.67 | -35.28 | 2.40 | False |
| Q4A_Q4A | gender | Very bad | 11.37 | 3.53 | -6.50 | False |
| Q46F_Q47F | location | Very badly | 9.52 | 4.14 | 15.20 | True |
| Q46F_Q47F | gender | Very badly | 7.84 | -8.90 | -3.30 | False |

## Spread and full answer distributions

The JSON report includes every subgroup option, raw counts, weighted counts and spread measures.

### Q38E_Q38E

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Police?

Spread, unweighted: `{"tvd_pp": 44.875, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.5, "tail_gap_pp": -21.5, "modal_ours_pct": 71.875, "modal_real_pct": 48.9, "modal_excess_pp": 22.975, "pass": false}`
Spread, weighted: `{"tvd_pp": 36.75099741512582, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.5, "tail_gap_pp": -21.5, "modal_ours_pct": 63.75099741512582, "modal_real_pct": 48.9, "modal_excess_pp": 14.850997415125825, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 2.00 |
| Some of them | 23 | 63.75 | 27.00 |
| Most of them | 9 | 36.25 | 48.90 |
| All of them | 0 | 0.00 | 19.50 |
| Refused | 0 | 0.00 | 1.70 |
| Don't know/Haven't heard | 0 | 0.00 | 0.90 |

### Q38F_Q38F

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Judges and magistrates?

Spread, unweighted: `{"tvd_pp": 62.224999999999994, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 17.299999999999997, "tail_gap_pp": -17.299999999999997, "modal_ours_pct": 65.625, "modal_real_pct": 45.6, "modal_excess_pp": 20.025, "pass": false}`
Spread, weighted: `{"tvd_pp": 65.0764168647681, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 17.299999999999997, "tail_gap_pp": -17.299999999999997, "modal_ours_pct": 68.47641686476811, "modal_real_pct": 45.6, "modal_excess_pp": 22.87641686476811, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 4.60 |
| Some of them | 11 | 31.52 | 45.60 |
| Most of them | 0 | 0.00 | 33.70 |
| All of them | 0 | 0.00 | 12.70 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard | 21 | 68.48 | 3.40 |

### Q38G_Q38G

How many of the following people do you think are involved in corruption, or haven't you heard enough about them to say: Tax officials, like officials from the South African Revenue Service or SARS?

Spread, unweighted: `{"tvd_pp": 37.875, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.9, "tail_gap_pp": -21.9, "modal_ours_pct": 65.625, "modal_real_pct": 36.8, "modal_excess_pp": 28.825000000000003, "pass": false}`
Spread, weighted: `{"tvd_pp": 40.43530201386477, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 21.9, "tail_gap_pp": -21.9, "modal_ours_pct": 64.23929160569816, "modal_real_pct": 36.8, "modal_excess_pp": 27.43929160569816, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| None | 0 | 0.00 | 5.80 |
| Some of them | 21 | 64.24 | 36.80 |
| Most of them | 5 | 13.06 | 31.60 |
| All of them | 0 | 0.00 | 16.10 |
| Don't know/Haven't heard | 6 | 22.70 | 9.70 |

### Q37F_Q37F

How much do you trust each of the following, or haven't you heard enough about them to say: Opposition political parties?

Spread, unweighted: `{"tvd_pp": 35.383366633366634, "tail_mass_ours_pct": 31.25, "tail_mass_real_pct": 43.25674325674326, "tail_gap_pp": -12.006743256743263, "modal_ours_pct": 65.625, "modal_real_pct": 36.56343656343657, "modal_excess_pp": 29.061563436563432, "pass": false}`
Spread, weighted: `{"tvd_pp": 33.969397145389216, "tail_mass_ours_pct": 33.662970486978416, "tail_mass_real_pct": 43.25674325674326, "tail_gap_pp": -9.593772769764847, "modal_ours_pct": 66.33702951302158, "modal_real_pct": 36.56343656343657, "modal_excess_pp": 29.77359294958501, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 10 | 33.66 | 36.56 |
| Just a little | 21 | 66.34 | 32.37 |
| Somewhat | 0 | 0.00 | 23.38 |
| A lot | 0 | 0.00 | 6.69 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 1 | 0.00 | 1.00 |

### Q37I_Q37I

How much do you trust each of the following, or haven't you heard enough about them to say: Courts of law?

Spread, unweighted: `{"tvd_pp": 39.5, "tail_mass_ours_pct": 9.375, "tail_mass_real_pct": 36.9, "tail_gap_pp": -27.525, "modal_ours_pct": 71.875, "modal_real_pct": 33.8, "modal_excess_pp": 38.075, "pass": false}`
Spread, weighted: `{"tvd_pp": 37.22943731231331, "tail_mass_ours_pct": 11.884490816237804, "tail_mass_real_pct": 36.9, "tail_gap_pp": -25.015509183762195, "modal_ours_pct": 70.34384604237158, "modal_real_pct": 33.8, "modal_excess_pp": 36.543846042371584, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 3 | 11.88 | 21.10 |
| Just a little | 23 | 70.34 | 33.80 |
| Somewhat | 5 | 15.39 | 27.60 |
| A lot | 0 | 0.00 | 15.80 |
| Don't know/Haven't heard enough to say | 1 | 2.39 | 1.70 |

### Q37B_Q37B

How much do you trust each of the following, or haven't you heard enough about them to say: Parliament?

Spread, unweighted: `{"tvd_pp": 16.622580645161293, "tail_mass_ours_pct": 48.38709677419355, "tail_mass_real_pct": 44.2, "tail_gap_pp": 4.187096774193549, "modal_ours_pct": 48.38709677419355, "modal_real_pct": 39.2, "modal_excess_pp": 9.187096774193549, "pass": true}`
Spread, weighted: `{"tvd_pp": 19.224912200938796, "tail_mass_ours_pct": 50.62217756159358, "tail_mass_real_pct": 44.2, "tail_gap_pp": 6.422177561593578, "modal_ours_pct": 50.62217756159358, "modal_real_pct": 39.2, "modal_excess_pp": 11.422177561593578, "pass": true}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 15 | 50.62 | 39.20 |
| Just a little | 13 | 42.30 | 34.50 |
| Somewhat | 3 | 7.08 | 20.20 |
| A lot | 0 | 0.00 | 5.00 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 1.10 |

### Q46E_Q47E

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Narrowing gaps between rich and poor?

Spread, unweighted: `{"tvd_pp": 25.23548387096774, "tail_mass_ours_pct": 58.06451612903226, "tail_mass_real_pct": 76.9, "tail_gap_pp": -18.835483870967742, "modal_ours_pct": 58.06451612903226, "modal_real_pct": 76.4, "modal_excess_pp": -18.335483870967742, "pass": false}`
Spread, weighted: `{"tvd_pp": 25.985514855229418, "tail_mass_ours_pct": 57.31448514477058, "tail_mass_real_pct": 76.9, "tail_gap_pp": -19.585514855229427, "modal_ours_pct": 57.31448514477058, "modal_real_pct": 76.4, "modal_excess_pp": -19.085514855229427, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 18 | 57.31 | 76.40 |
| Fairly badly | 13 | 42.69 | 16.70 |
| Fairly well | 0 | 0.00 | 4.90 |
| Very well | 0 | 0.00 | 0.50 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 1.50 |

### Q46B_Q47B

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Improving the living standards of the poor?

Spread, unweighted: `{"tvd_pp": 32.20407907907909, "tail_mass_ours_pct": 43.75, "tail_mass_real_pct": 71.07107107107107, "tail_gap_pp": -27.321071071071074, "modal_ours_pct": 53.125, "modal_real_pct": 69.96996996996997, "modal_excess_pp": -16.844969969969966, "pass": false}`
Spread, weighted: `{"tvd_pp": 29.444773731124467, "tail_mass_ours_pct": 49.634305347954616, "tail_mass_real_pct": 71.07107107107107, "tail_gap_pp": -21.43676572311646, "modal_ours_pct": 50.36569465204539, "modal_real_pct": 69.96996996996997, "modal_excess_pp": -19.604275317924575, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 14 | 49.63 | 69.97 |
| Fairly badly | 17 | 50.37 | 20.92 |
| Fairly well | 1 | 0.00 | 7.51 |
| Very well | 0 | 0.00 | 1.10 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.50 |

### Q9A_Q10A

In this country, how free are you to say what you think?

Spread, unweighted: `{"tvd_pp": 58.9, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 58.099999999999994, "tail_gap_pp": -58.099999999999994, "modal_ours_pct": 56.25, "modal_real_pct": 43.1, "modal_excess_pp": 13.149999999999999, "pass": false}`
Spread, weighted: `{"tvd_pp": 58.9, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 58.099999999999994, "tail_gap_pp": -58.099999999999994, "modal_ours_pct": 52.67181439176702, "modal_real_pct": 43.1, "modal_excess_pp": 9.57181439176702, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all free | 0 | 0.00 | 15.00 |
| Not very free | 14 | 47.33 | 18.00 |
| Somewhat free | 18 | 52.67 | 23.10 |
| Completely free | 0 | 0.00 | 43.10 |
| Refused | 0 | 0.00 | 0.40 |
| Don't know | 0 | 0.00 | 0.40 |

### Q5A_Q5A

Looking back, how do you rate the following compared to 12 months ago: Economic condition of this country?

Spread, unweighted: `{"tvd_pp": 60.8, "tail_mass_ours_pct": 6.25, "tail_mass_real_pct": 35.300000000000004, "tail_gap_pp": -29.050000000000004, "modal_ours_pct": 87.5, "modal_real_pct": 34.2, "modal_excess_pp": 53.3, "pass": false}`
Spread, weighted: `{"tvd_pp": 60.149708808695145, "tail_mass_ours_pct": 6.30738727353225, "tail_mass_real_pct": 35.300000000000004, "tail_gap_pp": -28.992612726467755, "modal_ours_pct": 86.84970880869514, "modal_real_pct": 34.2, "modal_excess_pp": 52.64970880869514, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Much worse | 2 | 6.31 | 34.20 |
| Worse | 28 | 86.85 | 26.70 |
| Same | 1 | 3.26 | 28.80 |
| Better | 1 | 3.58 | 9.10 |
| Much better | 0 | 0.00 | 1.10 |
| Don't know | 0 | 0.00 | 0.10 |

### Q47A_Q48A

Do you approve or disapprove of the way that the following people have performed their jobs over the past 12 months, or haven't you heard enough about them to say: President Cyril Ramaphosa?

Spread, unweighted: `{"tvd_pp": 55.825, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 41.699999999999996, "tail_gap_pp": -41.699999999999996, "modal_ours_pct": 87.5, "modal_real_pct": 33.8, "modal_excess_pp": 53.7, "pass": false}`
Spread, weighted: `{"tvd_pp": 55.73176632004858, "tail_mass_ours_pct": 0.0, "tail_mass_real_pct": 41.699999999999996, "tail_gap_pp": -41.699999999999996, "modal_ours_pct": 87.1044305083999, "modal_real_pct": 33.8, "modal_excess_pp": 53.3044305083999, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Strongly disapprove | 0 | 0.00 | 33.80 |
| Disapprove | 28 | 87.10 | 32.30 |
| Approve | 3 | 9.47 | 23.30 |
| Strongly approve | 0 | 0.00 | 7.90 |
| Refused | 0 | 0.00 | 0.20 |
| Don't know or haven't heard enough to say | 1 | 3.43 | 2.50 |

### Q37G_Q37G

How much do you trust each of the following, or haven't you heard enough about them to say: The police?

Spread, unweighted: `{"tvd_pp": 45.629370629370634, "tail_mass_ours_pct": 18.75, "tail_mass_real_pct": 52.54745254745256, "tail_gap_pp": -33.79745254745256, "modal_ours_pct": 75.0, "modal_real_pct": 40.55944055944056, "modal_excess_pp": 34.44055944055944, "pass": false}`
Spread, weighted: `{"tvd_pp": 42.10568571369447, "tail_mass_ours_pct": 19.055451235724735, "tail_mass_real_pct": 52.54745254745256, "tail_gap_pp": -33.49200131172782, "modal_ours_pct": 71.47631508432384, "modal_real_pct": 40.55944055944056, "modal_excess_pp": 30.916874524883283, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 6 | 19.06 | 40.56 |
| Just a little | 24 | 71.48 | 29.37 |
| Somewhat | 2 | 9.47 | 17.68 |
| A lot | 0 | 0.00 | 11.99 |
| Refused | 0 | 0.00 | 0.10 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.30 |

### Q37A_Q37A

How much do you trust each of the following, or haven't you heard enough about them to say: The president?

Spread, unweighted: `{"tvd_pp": 26.674999999999997, "tail_mass_ours_pct": 62.5, "tail_mass_real_pct": 49.8, "tail_gap_pp": 12.700000000000003, "modal_ours_pct": 62.5, "modal_real_pct": 39.5, "modal_excess_pp": 23.0, "pass": false}`
Spread, weighted: `{"tvd_pp": 29.800000000000004, "tail_mass_ours_pct": 66.20444730459397, "tail_mass_real_pct": 49.8, "tail_gap_pp": 16.404447304593972, "modal_ours_pct": 66.20444730459397, "modal_real_pct": 39.5, "modal_excess_pp": 26.70444730459397, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Not at all | 20 | 66.20 | 39.50 |
| Just a little | 11 | 33.80 | 30.70 |
| Somewhat | 1 | 0.00 | 18.90 |
| A lot | 0 | 0.00 | 10.30 |
| Refused | 0 | 0.00 | 0.00 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.60 |

### Q4A_Q4A

In general, how would you describe the present economic condition of this country?

Spread, unweighted: `{"tvd_pp": 26.326326326326328, "tail_mass_ours_pct": 59.375, "tail_mass_real_pct": 58.05805805805806, "tail_gap_pp": 1.3169419419419413, "modal_ours_pct": 59.375, "modal_real_pct": 51.85185185185185, "modal_excess_pp": 7.523148148148152, "pass": true}`
Spread, weighted: `{"tvd_pp": 26.32632632632633, "tail_mass_ours_pct": 59.22532484940757, "tail_mass_real_pct": 58.05805805805806, "tail_gap_pp": 1.1672667913495118, "modal_ours_pct": 59.22532484940757, "modal_real_pct": 51.85185185185185, "modal_excess_pp": 7.373472997555723, "pass": true}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very bad | 19 | 59.23 | 51.85 |
| Fairly bad | 13 | 40.77 | 21.82 |
| Neither good nor bad | 0 | 0.00 | 6.31 |
| Fairly good | 0 | 0.00 | 12.71 |
| Very good | 0 | 0.00 | 6.21 |
| Refused | 0 | 0.00 | 0.10 |
| Don't know | 0 | 0.00 | 1.00 |

### Q46F_Q47F

How well or badly would you say the current government is handling the following matters, or haven't you heard enough to say: Reducing crime?

Spread, unweighted: `{"tvd_pp": 48.074999999999996, "tail_mass_ours_pct": 37.5, "tail_mass_real_pct": 82.0, "tail_gap_pp": -44.5, "modal_ours_pct": 59.375, "modal_real_pct": 79.8, "modal_excess_pp": -20.424999999999997, "pass": false}`
Spread, weighted: `{"tvd_pp": 50.63652728830832, "tail_mass_ours_pct": 35.73570311420436, "tail_mass_real_pct": 82.0, "tail_gap_pp": -46.26429688579564, "modal_ours_pct": 61.93652728830832, "modal_real_pct": 79.8, "modal_excess_pp": -17.863472711691678, "pass": false}`

| Answer | Raw count | Weighted share | Real share |
|---|---:|---:|---:|
| Very badly | 12 | 35.74 | 79.80 |
| Fairly badly | 19 | 61.94 | 11.30 |
| Fairly well | 1 | 2.33 | 6.50 |
| Very well | 0 | 0.00 | 2.20 |
| Don't know/Haven't heard enough to say | 0 | 0.00 | 0.20 |

## Eligibility correction

The original 40-person room included eight minors. R10 covers adults. This is a post-hoc sensitivity analysis of the 32 adults already asked, with no new calls, no changed answers and no outcome-based exclusions. Weights were refitted on the full adult library. Original trial results remain separately preserved. This is not the originally planned 40-adult trial.

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
