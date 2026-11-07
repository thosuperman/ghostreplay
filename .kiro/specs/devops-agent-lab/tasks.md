# Implementation plan — DevOps Agent Lab

- [x] 1. Package skeleton `devops-agent-lab` depending on `ghostreplay` (workspace)
- [x] 2. `MockAwsCloud` fixture + `health_checks` condition
- [x] 3. Tools (read-only, destructive, proposal) with argument models
- [x] 4. Scripted SRE model policy
- [x] 5. Agent harness + `SafetyGate` for the fixed variant
- [x] 6. Invariants (verification, capacity, approval, errors surfaced)
- [x] 7. Scenario + fault presets + CLI (`run`, `serve`, `demo`)
- [x] 8. Tests: incident fails, counterfactual vulnerable FAIL / fixed PASS, no destructive call in fixed
