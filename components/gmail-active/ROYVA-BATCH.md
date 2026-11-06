# Request-scoped Gmail batch mutations

`batch_modify_messages` accepts1–1000unique explicit message IDs and label additions/removals, then submits ONE Gmail batchModify call. It performs no searches or automatic page expansion. Empty/implicit/duplicate/oversized IDs, empty label changes and conflicting labels are rejected before Gmail access.

OpenCode permission action gmail_batch_modify_messages is ask. Telegram /approve uses decision:once bound to the exact pending request. It does not save an always rule or authorize later batches/pages/requests. Existing single-message changes remain ask. Approval prompts show batch count, exact message IDs and cached subject/sender when available, exact label arguments and a one-batch-only notice.

Gmail returns an empty success response, so the result reports submitted_count, not an independently verified changed count. No blind retries or automatic continuation are added. Tests mock all Gmail writes; a live inert native permission test verifies once leaves parallel/later/new-session requests gated. No real email mutations are necessary for these tests.

Validation: npm run build; node --experimental-test-module-mocks --test tests/*.test.mjs.
