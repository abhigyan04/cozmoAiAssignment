### video tier

| metric | value |
|---|---|
| rooms_matched | 2/4 |
| footprint_m2 | 43.12 vs tape 46.86 (-8.0%) |
| wall_mean_abs_err_pct | 12.1 |
| wall_max_abs_err_pct | 20.55 |
| wall_gate | 0/16 within +-3% |
| wall_inside_ci95 | 6/16 |
| ceiling_within_1.5cm | 0/0 |
| openings_within_2cm | 0/5 (missed 3, phantom 1) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom2 | A | 3.62 | 2.908 | -71.2 | 47.1 | **no** |
| bedroom2 | C | 3.66 | 2.908 | -75.2 | 47.1 | **no** |
| bedroom2 | B | 3.06 | 2.822 | -23.8 | 44.2 | yes |
| bedroom2 | D | 3.12 | 2.822 | -29.8 | 44.2 | yes |
| bedroom1 | A | 4.12 | 4.570 | +45.0 | 89.6 | yes |
| bedroom1 | C | 4.17 | 4.570 | +40.0 | 89.6 | yes |
| bedroom1 | B | 3.68 | 4.041 | +36.1 | 79.2 | yes |
| bedroom1 | D | 3.71 | 4.041 | +33.1 | 79.2 | yes |