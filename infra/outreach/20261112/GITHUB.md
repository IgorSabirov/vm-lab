Target: https://github.com/github/gh-aw/issues/74970

Thank you for the distinction between gh-aw alias resolution and native Copilot Auto. I can add a bounded real-world case and offer a public reproduction workflow for the native-Auto design work.

In IgorSabirov/vm-lab, gh-aw v1.2.2 with Copilot CLI 1.0.103 failed on the tested fixed-model route with `502 model_fallback_exhausted`. A direct native `--model auto` control using the same account succeeded; a subsequent native report run produced useful output in 21.379 seconds. This supports a route/configuration distinction, but does not by itself isolate every AWF variable or establish that all Free accounts behave the same way.

Recorded diagnosis and run links:
https://github.com/IgorSabirov/vm-lab/blob/main/infra/copilot/reports/CONNECTION_DIAGNOSIS_20261112.md

We kept this as a separate report-only pilot: fixed scientific source context, no agent tools or write token, a bounded invocation, a trusted publisher, and validation of the actual publication SHA. After correcting the repository Actions PR setting, Actions itself opened PR #27 from the saved report, without another model call:
https://github.com/IgorSabirov/vm-lab/pull/27

Our use case is scientific source comparison and registry maintenance: the agent must retain the difference between a source claim, an independently verified result and an unresolved prerequisite. The pilot does not yet implement arbitrary registry edits or autonomous scientific execution.

We would like to contribute this as a small public integration case. Is there a tracking issue or supported recipe for native Auto with AWF's credential isolation, concrete-model observation and budget accounting? We can help test a bounded candidate against the existing saved-output publication path. We are not proposing a firewall bypass or asking to expand model entitlements.

Prepared with GPT assistance and posted at the repository owner's direction.
