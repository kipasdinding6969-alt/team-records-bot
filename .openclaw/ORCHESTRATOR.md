# Team Records Bot V2 — Multi-Model Agent Orchestration

## Architecture (v2 — 2026-04-03)

```
┌─ OpenClaw :18789 (THE LION — Claude Opus 4.6) ──────────┐
│  Auth: ~/.claude/.credentials.json (auto-refresh)        │
│  Role: Lead orchestrator, engineering authority           │
│  Cron: morning briefing, dev journal, weekly analysis     │
│  Memory: nomic-embed-text semantic search                 │
│  MCP: filesystem, github, context7, obsidian-rest         │
│  Agency: 18 active agents from 104-agent fleet            │
│  Dispatch: backup-chain.sh (4-tier fallback)              │
└──────────┬────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────┐
     │  OpenCode serve :4096 (Tier 2 execution engine)    │
     │  systemd: opencode-serve.service                    │
     │  Auth: baiwan / QianHub2026!                        │
     │  Plugin: opencode-claude-auth (Claude Max sub)      │
     │                                                     │
     │  Claude Opus 4.6 → engineering tasks                │
     │  big-pickle → fallback engineering                  │
     │  qwen3.6-plus-free → 1M context reading            │
     │  nemotron-3-super → reasoning fallback              │
     │                                                     │
     │  Built-in: bash, file ops, pyright LSP, grep        │
     │  REST API: /session, /session/:id/message           │
     └────────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────┐
     │  Gemini 3.1 Pro (Tier 3 — research & planning)    │
     │  google-gemini-cli → Google OAuth auto-refresh      │
     │  (fmuhd3685@gmail.com)                              │
     │  Cost: FREE                                         │
     │  Used for: research, architecture, planning, audits │
     └────────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────┐
     │  Ollama :11434 (Tier 4 — local, offline)           │
     │  systemd: ollama.service                            │
     │                                                     │
     │  josiefied-qwen2.5-7b → quick checks, fallback    │
     │  nomic-embed-text → RAG embeddings (768-dim)       │
     │                                                     │
     │  RAG: local_rag/search.sh (fast lookup)            │
     │       local_rag/query.sh (search + LLM answer)     │
     │       local_rag/index.py (34,752 chunks indexed)   │
     └────────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────┐
     │  Tier 5: Queue + Telegram notify                   │
     │  .openclaw/queue/ → JSON task files                │
     │  Telegram chat: 7715010221                          │
     │  Picked up on next heartbeat or manual check        │
     └────────────────────────────────────────────────────┘
```

## Backup Chain (backup-chain.sh)

```
Engineering tasks:
  Claude Opus (OpenClaw) → Claude Opus (OpenCode) → Gemini 3.1 Pro → Ollama 7b → Queue+Notify

Research tasks:
  Gemini 3.1 Pro → Claude Opus (OpenClaw) → Claude Opus (OpenCode) → Ollama 7b → Queue+Notify
```

## Active Agents (18 of 104)

### Engineering (8)
| Agent | Use For | Model Tier |
|-------|---------|-----------|
| **backend-architect** | API design, schema decisions | Claude Opus |
| **frontend-developer** | React/TS dashboard | Claude Opus |
| **senior-developer** | Cross-cutting concerns | Claude Opus |
| **code-reviewer** | Quality gates, PR review | Claude Opus |
| **database-optimizer** | Query optimization, indexing | Claude Opus |
| **security-engineer** | SQL injection, auth hardening | Claude Opus |
| **software-architect** | Domain modeling, system design | Gemini |
| **devops-automator** | CI/CD, deployment | Gemini |

### Testing (5)
| Agent | Use For | Model Tier |
|-------|---------|-----------|
| **qa-engineer** | Test strategy, pytest | Claude Opus |
| **automation-engineer** | Test automation | Gemini |
| **api-tester** | API contract verification | Claude Opus |
| **evidence-collector** | Screenshot UI verification | Gemini |
| **test-results-analyzer** | Failure analysis | Ollama |

### Operations (3)
| Agent | Use For | Model Tier |
|-------|---------|-----------|
| **multi-ai-coordinator** | Agent handoff protocol | Gemini |
| **telegram-operations-specialist** | Bot features | Claude Opus |
| **docker-infrastructure-manager** | Container orchestration | Gemini |

### Specialized (2)
| Agent | Use For | Model Tier |
|-------|---------|-----------|
| **agents-orchestrator** | Pipeline coordination | Gemini |
| **mcp-builder** | MCP tool integration | Gemini |

## Phase 1 Agents (Original Fleet)

| Agent | Target | Status |
|-------|--------|--------|
| **role-doctor** | Fix role string mismatches | ✅ DONE (Phase 38: maintainer_id standardized) |
| **api-contract** | Verify frontend ↔ backend contracts | Phase 2 |
| **sheet-verifier** | Validate sheet sync data pipeline | Phase 2 |
| **ui-auditor** | Verify dashboard pages per role | Phase 3 |
| **test-builder** | Write tests for 21 untested modules | Phase 4 |

## Model Routing — Right Tool for Right Work

| Work Type | Model | Why |
|-----------|-------|-----|
| Code edits, fixes, refactoring | **Claude Opus 4.6** | Best reasoning, tool use |
| API contract verification | **Claude Opus 4.6** | Needs frontend + backend understanding |
| Test writing | **Claude Opus 4.6** | Tests need production quality |
| Architecture planning | **Gemini 3.1 Pro** | Free, strong analysis |
| Research / reading | **Gemini 3.1 Pro** | Free, large context |
| Codebase search | **nomic-embed-text** | 768-dim embeddings, cosine similarity |
| Quick syntax check | **josiefied-7b** | Instant, local, zero cost |
| Reasoning fallback | **nemotron-3-super** | When Claude is down |
| Reading 5000+ line files | **qwen3.6-plus-free** | 1M context window |

## RAG Integration

```bash
# Fast file lookup (no LLM, just embeddings)
./local_rag/search.sh "kill system knife deposit" 10

# Full RAG: search + LLM-generated answer
./local_rag/query.sh "how does role assignment work"

# Refresh index after code changes
python3 ./local_rag/index.py
```

Agents MUST run `local_rag/search.sh` before modifying code to understand context.

## Scripts

| Script | Purpose |
|--------|---------|
| `.openclaw/backup-chain.sh <msg> [type] [timeout]` | 4-tier fallback execution |
| `.openclaw/run-agent.sh <agent-id>` | Spawn agent via OpenCode + fallback |
| `.openclaw/router.sh <task-type> <message>` | Route task to right model |
| `local_rag/search.sh <query> [top_k]` | Fast semantic file lookup |
| `local_rag/query.sh <query>` | Semantic search + LLM answer |
| `local_rag/index.py` | Rebuild embeddings index |

## Services

| Service | Port | Status |
|---------|------|--------|
| OpenClaw gateway | :18789 | ✅ active |
| OpenCode serve | :4096 | ✅ active |
| Ollama | :11434 | ✅ active |

## Completion Criteria

1. All 3 role systems use consistent, joinable strings ✅ (Phase 38)
2. `maintenance_id` standardized across all tables ✅ (Phase 38)
3. Every frontend API call gets the response shape it expects ✅ (Phase 2 — api-contract audit, 2 bugs fixed)
4. Sheet sync produces verifiable data in all 5 target tables ✅ (Phase 5 — cascading client match: primary → account_id → phone)
5. Every dashboard page shows real data for its intended role ✅ (Phase 3 — 23 pages audited, 7 fixed)
6. All 21 previously-untested modules have passing tests ✅ (Phase 4 + 4b — 63 test files, 1882 tests)
7. `pytest tests/` passes 100% ✅ (1882 passed, batched)
8. `npx tsc --noEmit` passes ✅
9. `npx vite build` succeeds ✅
10. 4-tier backup chain operational ✅
11. RAG semantic search operational ✅ (59,216 chunks)
