# Documentation images

These images explain the concept and show the synthetic proof-of-concept experience without browser
chrome. They contain synthetic data only and no live service coordinates.

| Filename | Purpose |
|---|---|
| `amc-iq-00.png` | Conceptual knowledge ecosystem surrounding the patient, care team, and research workflow |
| `amc-iq-01.png` | Concept framing: one oncology trial-readiness question spans several grounding domains |
| `amc-iq-02.png` | Mapping from clauses in the question to the evidence domains needed to answer them |
| `amc-iq-03.png` | Agentic retrieval pattern: iterative planning, source selection, evidence merging, and human review |
| `building-assessment-workflow.png` | Editable free-form question entry and optional question-bank examples, parallel IQ activity, and the Building Assessment timeline progressing through evidence matching and blocker detection |
| `final-trial-readiness-assessment.png` | Completed assessment with trial summary, criteria cards, open issues, bottom line, drafted next action, review status, and patient facts |
| `citations-and-assessment-steps.png` | Evidence packet with source links beside the specialist retrieval, deepening, reconciliation, and assessment trace |

The conceptual diagrams use `NCT-4324` as abbreviated illustration text. The runnable synthetic demo
uses `NCT99004324`; captions must preserve that distinction.

The README references:

```markdown
docs/images/amc-iq-00.png
docs/images/amc-iq-01.png
docs/images/amc-iq-02.png
docs/images/amc-iq-03.png
docs/images/building-assessment-workflow.png
docs/images/final-trial-readiness-assessment.png
docs/images/citations-and-assessment-steps.png
```

The GitHub Pages site also publishes `social-preview.png` as the 1280 x 640 Open Graph and social
link preview card.

Do not commit screenshots that show: real Azure endpoints, personal names not in the synthetic
cohort, local file paths, browser notifications, or production credentials.
