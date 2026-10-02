### photo tier

| metric | value |
|---|---|
| rooms_matched | 4/4 |
| footprint_m2 | 36.22 vs tape 46.86 (-22.7%) |
| wall_mean_abs_err_pct | 13.37 |
| wall_max_abs_err_pct | 40.92 |
| wall_gate | 11/16 within +-8% |
| wall_inside_ci95 | 12/16 |
| ceiling_within_1.5cm | 0/4 |
| openings_within_2cm | 1/11 (missed 7, phantom 2) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom1 | A | 4.12 | 2.986 | -113.4 | 58.5 | **no** |
| bedroom1 | C | 4.17 | 2.986 | -118.4 | 58.5 | **no** |
| bedroom1 | B | 3.68 | 3.464 | -21.6 | 67.9 | yes |
| bedroom1 | D | 3.71 | 3.464 | -24.6 | 67.9 | yes |
| bedroom2 | A | 3.62 | 3.475 | -14.5 | 68.1 | yes |
| bedroom2 | C | 3.66 | 3.475 | -18.5 | 68.1 | yes |
| bedroom2 | B | 3.06 | 2.973 | -8.7 | 58.3 | yes |
| bedroom2 | D | 3.12 | 2.973 | -14.7 | 58.3 | yes |
| hall | A | 0.92 | 0.858 | -6.2 | 18.8 | yes |
| hall | C | 0.93 | 0.858 | -7.2 | 18.8 | yes |
| hall | B | 5.62 | 3.356 | -226.4 | 66.8 | **no** |
| hall | D | 5.68 | 3.356 | -232.4 | 66.8 | **no** |
| living | A | 3.12 | 2.767 | -35.3 | 54.3 | yes |
| living | C | 2.98 | 2.767 | -21.3 | 54.3 | yes |
| living | B | 4.93 | 4.577 | -35.3 | 89.7 | yes |
| living | D | 4.95 | 4.577 | -37.3 | 89.7 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom1 | 2.67 | 2.445 | -22.5 | yes |
| bedroom2 | 2.64 | 2.431 | -20.9 | yes |
| hall | 2.64 | 2.504 | -13.6 | yes |
| living | 2.62 | 2.349 | -27.1 | yes |