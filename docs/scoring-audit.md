# Scoring audit and policy 2.0

The reported breakdown reproduces an overall score of 100 with the old formula.
The cause is the use of the stronger of experience and projects: projects at 100
discard experience at 25. The old semantic mapping also awarded 100 for `strong`.

Old CV-only formula:

```text
round(.30 * content + .20 * skills + .25 * max(experience, projects)
      + .10 * education + .15 * structure)
```

New CV-only formula:

```text
round(.30 * content + .20 * skills + .125 * experience + .125 * projects
      + .10 * education + .15 * structure)
```

Experience and projects now each contribute once. The combined allocation remains
25%. Missing CV categories remain in the formula at zero; a strong project does
not remove weak or absent experience. This intentionally changes the old policy
that let projects entirely substitute for experience. Students can earn credit
for projects and internships, assessed using evidence appropriate to their level.

For content=100, skills=100, experience=25, education=100, structure=100,
projects=100: old raw total=100; new raw total=90.625; new displayed score=91.
This numeric regression input tests aggregation independently of the new semantic
calibration, whose highest category value is 92.

## Complete path and audit findings

1. Gemini returns qualitative evidence judgments, not scores. The AI wire model
   discards any extra `overall_score`; the strict internal semantic model rejects it.
2. Central normalization canonicalizes qualitative labels into the strict model.
   Legacy `moderate`/`medium` becomes `adequate`; `high` becomes `strong`.
3. AnalysisService verifies evidence against the CV. Unsupported judgments become
   `unknown`, which receives zero. Keyword presence is not proof of proficiency.
4. ScoringService is the sole owner of the overall. It produces a breakdown,
   component values and effective weights. AnalysisService copies that overall
   directly into CVAnalysisResult; app.py renders that field directly.
5. Default weights were already fractions and summed to 1.0. This was not a
   percentage-scale bug. Configured weights must now also sum to 1.0; a config
   containing 30/20 instead of .30/.20 is rejected.
6. Projects participated in the old combined component; weaker experience had
   no independent effect. Both now participate independently, without a duplicate
   combined component.
7. Each CV category contributes once. Job requirements each belong to a single
   category. Job weights and match status points remain unchanged; semantic
   relevance caps use the new calibration.
8. The old bounded/clamped weighted sum was already normalized, so clamping did
   not cause this result. The new aggregator rejects invalid input scores and
   rounds its convex mean once, without clamping a potentially bad weighted sum.
9. JD absence selects CV-only scoring; a present JD selects job scoring. Only
   job scoring redistributes weights when a category has no JD requirements.
10. The frontend field was correct. Its label lookup incorrectly used match labels
    in CV-only mode. It now selects CV quality labels or job-match labels by mode.
    Styles are unchanged.

## Semantic calibration

| Level | Points |
|---|---:|
| exceptional | 92 |
| strong | 82 |
| adequate | 70 |
| limited | 52 |
| weak | 35 |
| insufficient | 15 |
| unknown (absent/unverifiable evidence) | 0 |

The prompt requires independent evidence for each category and reserves exceptional
for unusually compelling ownership, complexity and outcomes. A heading, skill
keyword or degree name alone does not justify strong or exceptional. The backend
maps levels; Gemini cannot submit a numeric score. Calibration controls points;
the frequency and accuracy of levels still depend on model judgment and should be
reviewed with real CVs.

Structure separately measures five binary contact/section checks and can be 100.
All five semantic categories at exceptional plus structure=100 produce 93, not
100. Fallback presence proxies are at most limited (52); its content heuristic is
capped at adequate (70). Neither fallback proxy establishes semantic excellence.

CV-only labels: 90–100 Exceptional, 80–89 Strong, 70–79 Solid, 60–69 Fair,
0–59 Needs Improvement. Job-match labels use the existing separate bands.

Scoring and prompt versions are now 2.0. Previously stored session results retain
their original score until analyzed again; restarting the local app clears those
old sessions.
