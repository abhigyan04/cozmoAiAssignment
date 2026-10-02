### video tier

| metric | value |
|---|---|
| rooms_matched | 2/4 |
| footprint_m2 | 30.77 vs tape 46.86 (-34.3%) |
| wall_mean_abs_err_pct | 12.51 |
| wall_max_abs_err_pct | 17.53 |
| wall_gate | 2/16 within +-3% |
| wall_inside_ci95 | 2/16 |
| ceiling_within_1.5cm | 0/1 |
| openings_within_2cm | 0/7 (missed 3, phantom 3) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom1 | A | 4.12 | 3.439 | -68.1 | 22.5 | **no** |
| bedroom1 | C | 4.17 | 3.439 | -73.1 | 22.5 | **no** |
| bedroom1 | B | 3.68 | 3.096 | -58.4 | 20.8 | **no** |
| bedroom1 | D | 3.71 | 3.096 | -61.4 | 20.8 | **no** |
| bedroom2 | A | 3.62 | 3.063 | -55.7 | 47.1 | **no** |
| bedroom2 | C | 3.66 | 3.063 | -59.7 | 47.1 | **no** |
| bedroom2 | B | 3.06 | 3.080 | +2.0 | 38.9 | yes |
| bedroom2 | D | 3.12 | 3.080 | -4.0 | 38.9 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom1 | 2.67 | 2.604 | -6.6 | yes |