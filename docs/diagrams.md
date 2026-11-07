# Diagrams

Rendered versions live in [`assets/`](assets/): `architecture.svg` and
`record-replay-sequence.svg`. The Mermaid sources below render on GitHub and are the
canonical text versions.

## Architecture

```mermaid
flowchart TB
  subgraph Apps["Independent applications"]
    S["Support Agent Lab<br/>Duplicate Refund"]
    D["DevOps Agent Lab<br/>Unsafe Infrastructure"]
    UI["Dashboard (React)"]
  end
  subgraph FW["packages/ghostreplay (shared framework)"]
    RT["AgentRuntime<br/>complete · call_tool · now · new_id"]
    SE["Session.interact<br/>record · replay · counterfactual · branch"]
    REC["Recorder + Redactor"]
    TR["ToolRegistry (allowlist)"]
    MA["ModelAdapter<br/>scripted | live"]
    MU["Mutation catalog"]
    DI["Diff engine"]
    RG["Regression: invariants → pytest"]
    ST["SQLite store · FastAPI · gateway"]
  end
  S --> RT
  D --> RT
  RT --> SE --> REC --> ST
  SE --> TR
  SE --> MA
  SE --> MU
  ST --> DI
  ST --> RG
  UI -->|HTTP / SSE| ST
```

## Record and replay

```mermaid
sequenceDiagram
  participant A as Agent
  participant R as AgentRuntime
  participant S as Session
  participant B as Simulated backend
  Note over A,B: Record
  A->>R: call_tool(name, args)
  R->>S: interact(op)
  S->>B: execute
  B-->>S: response + state
  S-->>A: response (event source = live, stored redacted)
  Note over A,B: Replay (offline)
  A->>R: call_tool(name, args)
  R->>S: interact(op)
  S->>S: next recorded interaction matches kind, name, key?
  S-->>A: recorded response (source = recorded)
  Note over S: mismatch → divergence event + ReplayDivergenceError (no guessing)
```

## Production deployment

The live demo at https://ghostreplay.hayaix.tech. Details:
[docs/deployment/ARCHITECTURE.md](deployment/ARCHITECTURE.md).

```mermaid
flowchart TB
  user([Visitor browser]) -->|HTTPS| dns[Route 53<br/>ghostreplay.hayaix.tech A 34.226.55.219]
  dns --> fw[Lightsail firewall + ufw<br/>80, 443 public · 22 admin only]
  subgraph vps[Lightsail ghostreplay-prod · us-east-1 · 2 GB · Ubuntu 24.04]
    fw --> caddy[Caddy<br/>TLS · security headers · static dashboard]
    caddy -->|/lab/support/*| sup[ghostreplay-support.service<br/>127.0.0.1:8101 · 1 worker]
    caddy -->|/lab/devops/*| dev[ghostreplay-devops.service<br/>127.0.0.1:8102 · 1 worker]
    sup --> fwk[(ghostreplay framework)]
    dev --> fwk
    sup --> sdb[(support-agent.sqlite3<br/>WAL · per-session rows)]
    dev --> ddb[(devops-agent.sqlite3<br/>WAL · per-session rows)]
    timers[backup timer · monitor timer] -.-> sdb
    timers -.-> ddb
  end
  sup -. blocked: IPAddressDeny=any .-> meta[instance metadata / AWS APIs / internet]
  dev -. blocked .-> meta
```
