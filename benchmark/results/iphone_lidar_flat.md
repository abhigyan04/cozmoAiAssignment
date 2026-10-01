### lidar tier

| metric | value |
|---|---|
| rooms_matched | 3/4 |
| footprint_m2 | 37.63 vs tape 46.86 (-19.7%) |
| wall_mean_abs_err_pct | 7.54 |
| wall_max_abs_err_pct | 25.95 |
| wall_gate | None |
| wall_inside_ci95 | 7/16 |
| ceiling_within_1.5cm | 1/3 |
| openings_within_2cm | 0/10 (missed 4, phantom 3) |

| room | wall | tape m | ours m | err cm | 95% CI ± cm | inside CI |
|---|---|---|---|---|---|---|
| bedroom2 | A | 3.62 | 3.612 | -0.8 | 8.3 | yes |
| bedroom2 | C | 3.66 | 3.612 | -4.8 | 8.3 | yes |
| bedroom2 | B | 3.06 | 3.022 | -3.8 | 8.3 | yes |
| bedroom2 | D | 3.12 | 3.022 | -9.8 | 8.3 | **no** |
| bedroom1 | A | 4.12 | 3.088 | -103.2 | 11.4 | **no** |
| bedroom1 | C | 4.17 | 3.088 | -108.2 | 11.4 | **no** |
| bedroom1 | B | 3.68 | 3.618 | -6.2 | 11.4 | yes |
| bedroom1 | D | 3.71 | 3.618 | -9.2 | 11.4 | yes |
| living | A | 3.12 | 3.486 | +36.6 | 11.4 | **no** |
| living | C | 2.98 | 3.486 | +50.6 | 11.4 | **no** |
| living | B | 4.93 | 4.922 | -0.8 | 11.4 | yes |
| living | D | 4.95 | 4.922 | -2.8 | 11.4 | yes |

| room | ceiling tape | ours | err cm | inside CI |
|---|---|---|---|---|
| bedroom2 | 2.64 | 2.645 | +0.5 | yes |
| bedroom1 | 2.67 | 2.048 | -62.2 | **no** |
| living | 2.50 | 2.685 | +18.5 | **no** |