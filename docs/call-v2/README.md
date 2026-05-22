# Call V2 Planning Docs

These documents define the planned v2 call runtime before implementation begins.

Recommended reading order:

1. [Architecture And Principles](./01-architecture-and-principles.md)
2. [Runtime State Machine](./02-runtime-state-machine.md)
3. [Event Contracts](./03-event-contracts.md)
4. [Agent Contract](./04-agent-contract.md)
5. [Speculative Endpointing](./05-speculative-endpointing.md)
6. [Cache Policy](./06-cache-policy.md)
7. [Testing And Simulator Plan](./07-testing-and-simulator-plan.md)
8. [Implementation Phases](./08-implementation-phases.md)

## Review Checklist

- Does v2 remain a general-purpose calling agent runtime?
- Are telephony, STT, endpointing, agent, TTS, cache, and persistence boundaries clear?
- Are speculative runs quarantined until turn confirmation?
- Are cache rules conservative enough to avoid brittle conversation behavior?
- Are simulator and seam gates strict enough to catch practical timing issues?
- Is the implementation order safe and testable one phase at a time?
- Are requested deviations being evaluated against the bigger architecture before implementation?
