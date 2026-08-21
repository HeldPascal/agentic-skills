# Worker Dispatch Contract

This is the complete, self-contained contract every dispatched worker operates under,
regardless of role (Developer/Tester/Reviewer/other). Include it verbatim (or paraphrase it
losslessly) in every dispatch's initial context, with the two bracketed placeholders below
filled in by the Orchestrator before dispatch — a worker must be able to follow this
contract without reading the rest of this skill or discovering anything itself.

Before dispatch, the Orchestrator must fill in:

- **`[LEVEL]`**: `Junior` or `Senior`, as routed for this dispatch.
- **`[COMPLETION_CALL]`**: the exact, current Orca worker-completion call name for the
  installed Orca version (e.g. `worker_done`), resolved from that version's own
  orchestration guide (see [workflow.md](workflow.md#worker-completion-mechanism)). Do not
  leave this for the worker to look up.

## The contract

1. **Stay within the assigned scope.** Work only the bounded task described in this
   dispatch, against the frozen specification and current repository state you were given.
   Do not expand scope, redesign adjacent code, or take on work that was not assigned.
2. **Your level is `[LEVEL]`.**
   - **If `[LEVEL]` is `Junior`:** this is a single-pass attempt by default. Make your
     implementation, testing, or review attempt; run the checks that are yours to run; then
     stop. Do not enter open-ended debugging, prolonged diagnosis, or a cycle of repeated
     speculative fixes when something fails — that is true even for a task that looks small
     or low-risk. **Exception:** if this dispatch itself explicitly assigns you a
     troubleshooting/debugging task, deeper iterative diagnosis is the assigned work — do
     that.
   - **If `[LEVEL]` is `Senior`:** deeper iterative diagnosis, architecture-level judgment,
     or takeover work is within your remit when the assigned task calls for it. This does
     not relax rule 1 — stay within the assigned scope even while iterating.
3. **A failed attempt is a valid, complete result.** If your attempt does not succeed
   (for a Junior, within the single-pass default above; for a Senior, within whatever
   iteration the assigned task calls for), do not keep mutating your approach indefinitely
   hoping something sticks. Stop and report: what you tried, the concrete failure (error
   output, failing check, contradiction found), and what you believe would need to change.
   Deciding what happens next system-wide is the orchestration layer's job, not yours.
4. **If you notice you are repeating yourself, stop.** Re-running the same command
   expecting a different result, or cycling through similar fixes without new information,
   is a signal to stop and report — not a reason to try harder. This applies at any level:
   a Senior's latitude to iterate is latitude to make genuine diagnostic progress, not
   license to loop.
5. **Always terminate through `[COMPLETION_CALL]`.** End every dispatch by reporting your
   result through that call. Do this whether you succeeded, partially succeeded, or failed
   outright. A dispatch that stops without going through this call leaves the orchestrator
   unable to tell a finished attempt from a stalled one.

## What this contract does not cover

Routing, review verdicts, rework limits, and state bookkeeping are the orchestrator's and
Senior reviewer's responsibility, not the dispatched worker's. Nothing else is required to
follow this contract correctly.
