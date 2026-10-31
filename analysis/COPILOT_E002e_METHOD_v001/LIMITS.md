# Copilot CLI limits checked 31 October 2026

Official sources:
- https://docs.github.com/en/copilot/get-started/plans
- https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing
- https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/usage-limits
- https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/set-session-limit
- https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference

Current individual billing uses AI credits based on model and input/output/cached tokens. A fixed count of messages is therefore not a reliable description of allowance. Free has an allowance and auto model selection, but these pages do not give its exact credit amount. The remaining balance for this particular account has not been obtained. Included credits reset on the first day of each month at 00:00 UTC (03:00 Moscow).

The existing bridge uses --max-ai-credits 30. This is a soft session ceiling, not a fixed charge or a purchase: a response in progress can finish past the threshold. We have not changed billing, subscribed or purchased additional credits. Service rate limits may apply independently.

No universal maximum duration of one foreground CLI answer was found in these references. The documented COPILOT_TASK_WAIT_TIMEOUT_SECONDS default 600 concerns waiting for background agents/shell work, not a general 10-minute answer deadline. Our text-only bridge disables those tools. It sets no model-call timeout without an explicit user instruction.

The 128 KiB prompt cap is our bridge's local input limit, not GitHub's advertised output limit. Model context/output limits are not permission for unlimited response length. This request explicitly asks for a concise response.
