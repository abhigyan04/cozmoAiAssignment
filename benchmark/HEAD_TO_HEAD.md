# Head-to-head: our LiDAR tier vs Polycam

Polycam for iOS **7.0.3** (free tier), iPhone 17 Pro LiDAR, same rooms, same evening. Exports: `data/raw/iphone/polycam/<room>/<room>.glb` (+ walkthrough video). Method and fairness notes: docstring of `scripts/head_to_head.py`.

| room | dimension | tape m | ours m | ours err cm | Polycam m | Polycam err cm | beat or tie |
|---|---|---|---|---|---|---|---|
| living | wall A | 3.12 | 3.487 | +36.7 | 3.050 | -7.0 | no |
| living | wall B | 4.93 | 4.922 | -0.8 | 4.970 | +4.0 | yes |
| living | wall C | 2.98 | 3.487 | +50.7 | 3.050 | +7.0 | no |
| living | wall D | 4.95 | 4.922 | -2.8 | 4.970 | +2.0 | yes |
| living | ceiling | 2.62 | 2.664 | +4.4 | 2.610 | -1.0 | no |
| bedroom1 | wall A | 4.12 | 3.088 | -103.2 | 3.670 | -45.0 | no |
| bedroom1 | wall B | 3.68 | 3.619 | -6.1 | 3.030 | -65.0 | yes |
| bedroom1 | wall C | 4.17 | 3.088 | -108.2 | 3.670 | -50.0 | no |
| bedroom1 | wall D | 3.71 | 3.619 | -9.1 | 3.030 | -68.0 | yes |
| bedroom1 | ceiling | 2.67 | 2.663 | -0.7 | 2.640 | -3.0 | yes |

**Beat or tie on 5/10 shared dimensions (50 %); gate: ≥ 70 %.**