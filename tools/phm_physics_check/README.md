# PHM Physics Check

Deterministic physics plausibility checker for LLM outputs, packaged as a
Dify tool plugin. Scans text for quantities with physical units and verifies
them against **universal physical laws**.

## What it checks

| Rule | Verdict | Example caught |
|---|---|---|
| Universal speed limit | FAIL | "travels at 4e9 m/s" |
| Absolute temperature floor | FAIL | "heated to -300 C" |
| Probability range [0,1] | FAIL | "confidence: 1.8" |
| Kinematics consistency | FAIL | v0=0, a=9.8, t=3 s, but v=50 m/s |
| Energy / momentum conservation | FAIL | output energy > input energy |
| Mass / length / energy non-negativity | FAIL | "mass = -3 kg" |
| Extreme acceleration | WARN | "accelerates at 1e7 m/s²" |

Unknown units are ignored by design — no false positives from jargon.

## Properties

- **Deterministic**: identical input always yields an identical verdict;
  results are reproducible and auditable by anyone.
- **Offline**: no network calls at check time; no data leaves the host.
- **Zero-dependency core**: the checking core uses only the Python standard
  library.
- **Sub-millisecond** per check.

## Usage in Dify

Add the tool to any agent or workflow. Pass the text to check (typically the
model's own output) and read the structured result:

```json
{
  "verdict": "FAIL",
  "n_quantities_checked": 3,
  "violations": [
    {"rule": "speed_exceeds_light", "severity": "FAIL",
     "detail": "Speed 4000000000.0 m/s exceeds c = 299792458 m/s",
     "location": "travels at 4.0e9 m/s"}
  ],
  "engine": "PHM-Lite",
  "deterministic": true
}
```

## Scope note

This plugin is the offline universal-law subset of the PHM physical-judgment
engine. Domain-specific profile checks (drone, vehicle, power-grid, and
molecular profiles) are provided by the full engine via separate deployment.

MIT License.
