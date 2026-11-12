---
applyTo: ".github/workflows/**,tools/**,infra/**"
---
Reuse existing tooling. Pin third-party actions by full SHA, minimize permissions,
bound jobs and keep untrusted text out of shell interpolation. Never run PR code
with a repository secret. Model-generated text is not an executable workflow.
Artifacts need provenance and honest execution status. Failed AI delivery is not
an empty successful review. Do not silently retry an unknown prior submission.
Changes made by GITHUB_TOKEN may not trigger ordinary PR CI: explicitly arrange
validation and never report unrun checks as green. Test the real event path.
