### photo tier

| metric | value |
|---|---|
| rooms_matched | 4/4 |
| footprint_m2 | 40.40 vs tape 46.86 (-13.8%) |
| wall_mean_abs_err_pct | 13.01 |
| wall_max_abs_err_pct | 55.11 |
| wall_gate | 8/16 within +-8% |
| wall_inside_ci95 | 12/16 |
| ceiling_within_1.5cm | 1/3 |
| openings_within_2cm | 1/12 (missed 8, phantom 3) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom1 | A | 4.12 | 3.605 | -51.5 | 70.7 | yes |
| bedroom1 | C | 4.17 | 3.605 | -56.5 | 70.7 | yes |
| bedroom1 | B | 3.68 | 2.982 | -69.8 | 58.5 | **no** |
| bedroom1 | D | 3.71 | 2.982 | -72.8 | 58.5 | **no** |
| bedroom2 | A | 3.62 | 3.771 | +15.1 | 73.9 | yes |
| bedroom2 | C | 3.66 | 3.771 | +11.1 | 73.9 | yes |
| bedroom2 | B | 3.06 | 3.071 | +1.1 | 60.2 | yes |
| bedroom2 | D | 3.12 | 3.071 | -4.9 | 60.2 | yes |
| hall | A | 0.92 | 1.009 | +8.9 | 19.8 | yes |
| hall | C | 0.93 | 1.009 | +7.9 | 19.8 | yes |
| hall | B | 5.62 | 2.550 | -307.0 | 51.9 | **no** |
| hall | D | 5.68 | 2.550 | -313.0 | 51.9 | **no** |
| living | A | 3.12 | 3.109 | -1.1 | 61.0 | yes |
| living | C | 2.98 | 3.109 | +12.9 | 61.0 | yes |
| living | B | 4.93 | 4.983 | +5.3 | 97.7 | yes |
| living | D | 4.95 | 4.983 | +3.3 | 97.7 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom1 | 2.67 | 2.507 | -16.3 | yes |
| bedroom2 | 2.64 | 2.629 | -1.1 | yes |
| living | 2.50 | 2.704 | +20.4 | yes |