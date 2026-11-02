# Subagent Task Contract

- task_id / run_id:
- Goal: one sentence, verifiable result
- Route: exact route name registered in the current delegation tool
- Tier / reason for choice / input size:
- Prerequisite tasks: none, or task_ids already returned and verified
- Given facts, interfaces, exact identifiers:
- Briefs / sources / materials to read first:
- Read scope:
- Write scope: exact files, or none
- Forbidden: re-delegation, out-of-scope writes, secret access, external publishing, auto commit/push, etc. Specify per task
- Tools/checks: tools currently available and runnable check commands
- Acceptance criteria: checkable list
- Resource targets: tool calls / time / retries. State that these are not hard caps
- End: exactly one of: criteria met, insufficient evidence, permission/environment blocker, assigned scope exhausted
- Report: status, key result, evidence, artifact paths, tests/checks, unresolved, scope_changes
- Unclear requirement: do not guess changes; return a blocker plus the minimum info needed

## Parent checks

- Is the route actually registered? Did I avoid inventing per-task arguments the tool does not accept?
- Runnable without siblings' outputs? Shared writes conflict-free?
- Is there a way to check real evidence rather than the child's status?

## Approval request template (to the user)

Use only for authority decisions (spend, external publishing, deletion, scope, preference, accepting a known risk). Establish technical correctness with evidence or review first; do not ask the user to vouch for it.

- Decision needed: one sentence, plain language, no unexplained jargon
- What happens if approved / if not:
- What could go wrong and how far it reaches:
- Reversible? Exact undo step:
- Cost:
- Verified beforehand: tests, evidence, or specialist (F1/F2) review results, and how findings were handled
- Recommendation and confidence: include what is still unverified
- What you actually need to judge: the one or two points that depend on your authority or preference
- Safe default if unsure: the reversible or minimal option

## Minimal output contract example

```json
{
  "status": "completed|partial|blocked",
  "result": "short summary",
  "evidence": [{"path_or_url": "exact path/URL", "check": "what was verified"}],
  "artifacts": [],
  "checks": [],
  "unresolved": []
}
```

The formal definition is `core/spec/output-contract.schema.json` (JSON Schema 2020-12); the example above is illustrative and the schema is authoritative. Optional fields: `end` (one of the four End values) and `scope_changes`. Rules the schema enforces: `completed` requires non-empty `evidence`; `partial` and `blocked` require non-empty `unresolved`; unknown fields are rejected.

Use it as follows:

- Put the schema in the task contract's Report field, or pass it as the delegation tool's output schema when the tool supports one. Required fields are only those the parent reads.
- The parent validates every returned report against the schema before treating it as `returned` (`core.contract.validate`). A schema failure means the report is unusable; ask the child to resend, do not repair it by guessing.
- Passing the schema does not make a report `verified`. Check the factuality of evidence, artifact paths, and test results separately.
