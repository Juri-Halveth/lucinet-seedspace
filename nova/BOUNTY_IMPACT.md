# Bounty impact sharpening

NOVA already preserves exact bytes, contradictory interpretations, parser differences and research receipts. Security research needs one additional distinction: an interesting flag is not automatically a bounty-ready vulnerability.

The local impact gate uses this progression:

```text
FLAG
→ REPRODUCED SIGNAL
→ IMPACT
→ ROOT CAUSE
→ REMEDIATION CONTROL
→ REPORT CANDIDATE
```

It checks eight gates: declared scope, safe reproduction environment, repeatability, negative control, concrete security impact, bound root cause, remediation control and bound evidence references.

Main states:

- `FLAG_ONLY`
- `REPRODUCED_SIGNAL`
- `IMPACT_CANDIDATE`
- `ROOT_CAUSE_CANDIDATE`
- `DUPLICATE_CANDIDATE`
- `REPORT_CANDIDATE`
- `SCOPE_HOLD`
- `UNSAFE_PROOF_HOLD`

Duplicate handling is intentionally narrow. NOVA hashes the declared invariant, trust boundary, code path, faulty decision and minimal fix, then compares only exact signatures in the operator-provided known-pattern corpus. A non-match does not prove global novelty because private program reports remain invisible.

Reward data is context only. NOVA exposes a program ceiling only when a separate candidate severity and basis are supplied, and labels that value `PROGRAM_CONTEXT_NOT_PAYOUT_PREDICTION`.

The assessor performs no target network access, no exploit execution and no report submission. `LIVE_PRODUCTION` is not a safe proof environment and is held rather than promoted.

## CLI

```bash
python nova/nova.py --workspace ./research bounty-impact nova/examples/bounty-impact-tron-synthetic.json
```

The example is a synthetic local fixture shaped around the public TRON DAO program policy. It is not a claim that TRON contains the synthetic bug.

## Why these gates exist

Current HackerOne guidance asks for reproducible steps, concrete impact and actionable information. HackerOne's report states also distinguish Informative from actionable findings and treat reports resolved by a single underlying fix as duplicates. Its systemic-issue standard gives additional value when a report changes the understood root cause, scope, exploitation technique or remediation strategy.

TRON DAO's current HackerOne policy requires reproducible detail, says to submit one vulnerability per report unless a chain is needed to show impact, awards only the first reproducible duplicate and groups multiple vulnerabilities caused by one underlying issue into one bounty. It also prohibits active exploitation against TRON networks.

References checked 2026-10-27:

- https://docs.hackerone.com/en/articles/8475116-quality-reports
- https://docs.hackerone.com/en/articles/8475030-report-states
- https://docs.hackerone.com/en/articles/8369826-detailed-platform-standards
- https://www.hackerone.com/policies/code-of-conduct
- https://hackerone.com/tron_dao
- https://github.com/tronprotocol/java-tron/security/policy

The public TRON page currently lists maximum reward figures of USD 2,000 / 10,000 / 25,000 / 100,000 for Low / Medium / High / Critical. Those figures can change and do not predict a specific payout.
