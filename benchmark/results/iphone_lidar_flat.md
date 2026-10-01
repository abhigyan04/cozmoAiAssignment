### lidar tier

| metric | value |
|---|---|
| rooms_matched | 3/4 |
| footprint_m2 | 36.55 vs tape 46.86 (-22.0%) |
| wall_mean_abs_err_pct | 8.19 |
| wall_max_abs_err_pct | 25.95 |
| wall_gate | None |
| wall_inside_ci95 | 6/16 |
| ceiling_within_1.5cm | 1/3 |
| openings_within_2cm | 0/10 (missed 4, phantom 3) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom2 | A | 3.62 | 3.473 | -14.7 | 12.6 | **no** |
| bedroom2 | C | 3.66 | 3.473 | -18.7 | 12.6 | **no** |
| bedroom2 | B | 3.06 | 3.021 | -3.9 | 11.4 | yes |
| bedroom2 | D | 3.12 | 3.021 | -9.9 | 11.4 | yes |
| bedroom1 | A | 4.12 | 3.088 | -103.2 | 11.4 | **no** |
| bedroom1 | C | 4.17 | 3.088 | -108.2 | 11.4 | **no** |
| bedroom1 | B | 3.68 | 3.619 | -6.1 | 11.4 | yes |
| bedroom1 | D | 3.71 | 3.619 | -9.1 | 11.4 | yes |
| living | A | 3.12 | 3.487 | +36.7 | 11.4 | **no** |
| living | C | 2.98 | 3.487 | +50.7 | 11.4 | **no** |
| living | B | 4.93 | 4.922 | -0.8 | 11.4 | yes |
| living | D | 4.95 | 4.922 | -2.8 | 11.4 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom2 | 2.64 | 2.645 | +0.5 | yes |
| bedroom1 | 2.67 | 2.048 | -62.2 | **no** |
| living | 2.62 | 2.685 | +6.5 | **no** |