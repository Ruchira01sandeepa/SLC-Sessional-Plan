# Age references for the physical tests

Provisional reference points for boys (U15, U17, U19), used to label each result *for the player's age* and as a fallback
when a level group is too small to rank (fewer than 5 players). They are references, not pass/fail standards.
Values live in `app/age_norms.py`; replace them with SLC's own percentiles as tested data builds up.

| Test | Unit | U15 dev / exp / strong | U17 dev / exp / strong | U19 dev / exp / strong | Basis |
|---|---|---|---|---|---|
| Standing broad jump | cm | 165.00 / 185.00 / 205.00 | 180.00 / 200.00 / 220.00 | 190.00 / 210.00 / 230.00 | published youth norms |
| 20 m sprint | s | 3.65 / 3.45 / 3.25 | 3.45 / 3.25 / 3.10 | 3.35 / 3.18 / 3.05 | published youth athlete data |
| Push-ups | valid reps | 14 / 20 / 28 | 18 / 25 / 33 | 20 / 28 / 36 | published youth norms |
| Inverted row | valid reps | 8 / 12 / 17 | 10 / 15 / 20 | 12 / 17 / 23 | estimate |
| 5-10-5 shuttle | s | 5.40 / 5.10 / 4.85 | 5.15 / 4.90 / 4.65 | 5.00 / 4.75 / 4.55 | estimate |
| Standard plank | s | 60.00 / 90.00 / 130.00 | 75.00 / 110.00 / 150.00 | 90.00 / 120.00 / 170.00 | published youth survey (means) |
| 2 km run | mm.ss | 9.30 / 8.50 / 8.15 | 9.00 / 8.25 / 7.55 | 8.45 / 8.10 / 7.40 | senior standard, scaled for age |
| Bronco | mm.ss | 6.15 / 5.50 / 5.25 | 6.00 / 5.35 / 5.10 | 5.50 / 5.25 / 5.00 | estimate |

Developing is about the 25th percentile, expected about the 50th, strong about the 75th. Labels: Below reference, Developing, On track, Strong for age.
Each age group also has its own typo-check range for imports (`PLAUSIBLE` in the same file).

## Sources

- Standing broad jump: Saint-Maurice et al. 2015, normative reference values for standing broad jump among Hungarian youth (https://www.ncbi.nlm.nih.gov/pubmed/26054955); Thomas et al. 2020, European Journal of Translational Myology (https://pmc.ncbi.nlm.nih.gov/articles/PMC7385687).
- 20 m sprint: pooled data on adolescent male rugby league players, weighted means by age (https://pmc.ncbi.nlm.nih.gov/articles/PMC7429421/table/table001). Cricketers set slightly slower.
- Push-ups: FitnessGram Healthy Fitness Zone, boys (https://www.rcboe.org//cms/lib/GA01903614/Centricity/Domain/17524/Fitnessgram.pdf); NCA-BCCI U19 male cricketers, North Zone (https://www.academia.edu/36207380/).
- Plank: CDC NCHS Data Brief 139, NHANES National Youth Fitness Survey 2012 (https://www.cdc.gov/nchs/products/databriefs/db139.htm).
- 2 km run: BCCI senior time-trial standard 8:15 to 8:30 (https://sportskeeda.com/cricket/news-bcci-introduce-2-km-fitness-test-indian-cricket-team-members); junior values scaled by age.
- 5-10-5 shuttle, inverted row, Bronco: no usable published youth tables were found; values are estimates and are marked as such in the app.

Girls: no references are set (none were found for these tests), so girls' results are shown without an age label.
