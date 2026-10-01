### photo tier

| metric | value |
|---|---|
| rooms_matched | 4/4 |
| footprint_m2 | 31.82 vs tape 46.86 (-32.1%) |
| wall_mean_abs_err_pct | 23.29 |
| wall_max_abs_err_pct | 81.95 |
| wall_gate | 7/16 within +-8% |
| wall_inside_ci95 | 8/16 |
| ceiling_within_1.5cm | 0/3 |
| openings_within_2cm | 0/13 (missed 8, phantom 4) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom1 | A | 4.12 | 2.985 | -113.5 | 58.5 | **no** |
| bedroom1 | C | 4.17 | 2.985 | -118.5 | 58.5 | **no** |
| bedroom1 | B | 3.68 | 3.469 | -21.1 | 68.0 | yes |
| bedroom1 | D | 3.71 | 3.469 | -24.1 | 68.0 | yes |
| bedroom2 | A | 3.62 | 2.767 | -85.3 | 54.8 | **no** |
| bedroom2 | C | 3.66 | 2.767 | -89.3 | 54.8 | **no** |
| bedroom2 | B | 3.06 | 2.916 | -14.4 | 57.8 | yes |
| bedroom2 | D | 3.12 | 2.916 | -20.4 | 57.8 | yes |
| hall | A | 0.92 | 0.700 | -22.0 | 19.5 | **no** |
| hall | C | 0.93 | 0.700 | -23.0 | 19.5 | **no** |
| hall | B | 5.62 | 1.025 | -459.5 | 24.4 | **no** |
| hall | D | 5.68 | 1.025 | -465.5 | 24.4 | **no** |
| living | A | 3.12 | 2.770 | -35.0 | 54.3 | yes |
| living | C | 2.98 | 2.770 | -21.0 | 54.3 | yes |
| living | B | 4.93 | 4.578 | -35.2 | 89.7 | yes |
| living | D | 4.95 | 4.578 | -37.2 | 89.7 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom1 | 2.67 | 1.968 | -70.2 | **no** |
| bedroom2 | 2.64 | 2.429 | -21.1 | yes |
| living | 2.62 | 2.370 | -25.0 | yes |