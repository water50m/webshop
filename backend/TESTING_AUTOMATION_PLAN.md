# Test plan: automatic chat replies and channel orders

## Safety gates

Each gate must pass before the next one is treated as complete.  All channel
calls are mocked until the final Meta Page smoke test.

1. **Parser rules** — Thai normalization, approved aliases, quantities,
   packaging, multiple items, substitutions, stock limits and ambiguous text.
2. **Safe answers** — only deterministic answers backed by available stock are
   sent; the identical answer is limited to two sends per conversation.
3. **Unsafe text** — unknown product, zero stock, delivery, payment exception,
   complaint, negotiation and general questions create an admin handoff and
   never send an automatic reply.
4. **Order lifecycle** — a channel message creates a pending draft; staff can
   edit it; confirmation re-checks stock, records stock movements, adds the
   accepted-order label and sends an order summary.
5. **External boundary** — mock the Messenger Send API for all automated tests.
   The live smoke test uses one staff-controlled Page account and one test
   customer, then confirms both the received reply and the Inbox audit record.

## Release criteria

- All automated tests pass.
- The Meta Page token, webhook signature secret and public HTTPS callback are
  configured; no token value is printed in test output.
- A staff-controlled live smoke test passes.  If these credentials or a test
  customer are unavailable, the service remains in local/test mode rather than
  sending to customers.
