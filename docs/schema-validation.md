# Gemini schema validation diagnosis

The initial requested run, `python -m pytest -vv --tb=long`, passed all 78 existing
tests. No existing failing test or captured live Gemini ValidationError was available.
The following failures were reproduced directly against the pre-change models with
synthetic response values; they are not claimed to be a captured production response.

## Exact pre-change validation failures

| Pydantic model / nested model | Field | Actual value | Expected value | Error type | Origin |
|---|---|---|---|---|---|
| AISemanticAnalysis / RequirementMatch | requirements.0.status | `"partially_matched"` | `"matched"`, `"partial"`, or `"missing"` | literal_error | Response variation (2); normalization missing at boundary (4) |
| AISemanticAnalysis / RequirementMatch | requirements.0.status | `"fully_matched"` | same three canonical statuses | literal_error | Response variation (2); normalization missing at boundary (4) |
| AISemanticAnalysis / RequirementMatch | requirements.0.status | `"not_demonstrated"` | same three canonical statuses | literal_error | Response variation (2); normalization missing at boundary (4) |
| AISemanticAnalysis / RequirementMatch | requirements.0.evidence | `null` / Python `None` | `list[str]` | list_type | Response variation (2); normalization missing at boundary (4) |
| AISemanticAnalysis | detected_skills | field omitted | required `list[str]` | missing | Internal schema correctly requires a list (3); wire defaults missing (4) |
| AISemanticAnalysis | strengths | field omitted | required `list[str]` | missing | Internal schema correctly requires a list (3); wire defaults missing (4) |
| AISemanticAnalysis | weaknesses | field omitted | required `list[str]` | missing | Internal schema correctly requires a list (3); wire defaults missing (4) |
| AISemanticAnalysis / SemanticJudgment | content_quality | `"strong"` | SemanticJudgment object with quality and evidence | model_type | Response shape variation (2); normalization missing (4) |
| AISemanticAnalysis / SemanticJudgment | content_quality | `null` / Python `None` | non-null SemanticJudgment object | model_type | Wire/internal optionality mismatch (2/3); normalization missing (4) |

For example, the exact enum failure was:

```text
1 validation error for AISemanticAnalysis
requirements.0.status
  Input should be 'matched', 'partial' or 'missing'
  [type=literal_error, input_value='partially_matched', input_type=str]
```

`"matched"` already passed. Optional relevance fields already accepted `None` in the
internal contract. The defect was using strict internal models as both the external
response schema and the first validation boundary. Internal restrictions were retained.

## Structured-output schema investigation (origin 1)

The pre-change Pydantic schema contained `$defs`, `$ref`, `anyOf`,
`additionalProperties: false`, defaults, a minimum string length, and priority bounds.
Their presence alone does **not** establish that Gemini rejected the schema.
Google documents a subset of JSON Schema and demonstrates references/unions;
see the [official structured-output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
There was no captured API schema rejection to classify as origin 1.

The production request now projects `AISemanticResponse` onto a small schema vocabulary:
objects, arrays, string/integer primitives, required fields, descriptions, and the
Google SDK's nullable representation. References are inlined. Default/validation
metadata are removed. Although local wire validation accepts bare string judgments,
the outgoing schema asks Gemini for canonical judgment objects.

This projection is checked through the installed Google GenAI SDK's complete
request/response conversion with the HTTP request mocked. That compatibility test
passed. It is an offline SDK check and does not establish live API acceptance.

## Validation pipeline

```text
Gemini JSON
  -> GeminiProvider validates AISemanticResponse
  -> centralized normalization
  -> strict AISemanticAnalysis
  -> existing evidence grounding and ScoringService
  -> strict CVAnalysisResult
```

Wire models have explicit types and discard extra external fields. No application
model was replaced with `dict[str, Any]`. All internal models in `backend/models.py`,
the frontend, scoring weights and scoring formulas are unchanged in this task.

## Normalization rules

| Incoming status | Internal status |
|---|---|
| matched, match, fully_matched, clearly_demonstrated | matched |
| partial, partially_matched, partially_demonstrated, some_evidence | partial |
| missing, not_found, not_demonstrated, no_evidence, not_mentioned, unknown, null/omitted | missing |

Labels accept case, whitespace and hyphen variations. Arbitrary statuses, such as
`"perfect"`, raise a typed error and trigger deterministic fallback rather than
earning points. The final internal RequirementMatch still rejects aliases and arbitrary
strings; only normalized canonical statuses enter it.

Omitted/null lists for skills, strengths, weaknesses, requirements, recommendations
and nested evidence normalize to `[]`. Invalid list shapes/elements remain errors.
Absent/null optional relevance is preserved as `None`; CV-only normalization removes
job-specific requirements and relevance. Absent/null quality judgments become an
explicit internal unknown judgment. A bare rating has no evidence and cannot earn
positive points after existing evidence grounding. Known quality levels are normalized;
unrecognized levels fail safely. Recommendation priorities are bounded to 1–10;
optional text receives conservative defaults, and the existing service still owns
all user-facing editing actions.

Malformed JSON, invalid primitive/container types, empty summaries, responses with
no semantic signals, invalid labels and failed internal validation trigger the existing
fallback with `ai_available=False`. Logs identify response_model, normalization,
internal_model or request_schema stages. Pydantic diagnostics include model, sanitized
field path and error type; input values, private CV text and exception contexts are
excluded.

## Verification and live limitation

`python -m pytest -vv --tb=long` passed 108 tests after implementation. Tests include
every requested variation, strict final models, malformed-response fallback, unchanged
scoring behavior, and actual provider/normalizer/service execution with mocked HTTP.

The execution process had no configured `GEMINI_API_KEY`. A live Gemini request could
not be verified. Offline SDK pipeline: PASS. Live Gemini pipeline: unverified; it
cannot honestly be reported as PASS without a configured key and a successful request.
