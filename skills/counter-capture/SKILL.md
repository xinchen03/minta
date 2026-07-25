---
name: counter-capture
description: Counter-example collection -- detects user correction signals and stores candidates via counter server (port 18720), with JSONL fallback queue. Supports /反例 manual registration and interactive guidance.
type: skill
---

# Counter-Capture Skill

## Architecture (R5C.P1)

```
UserPromptSubmit hook
  -> counter_capture.py: detect_correction_candidate()
  -> candidate saved to 18720 API or local JSONL queue
  -> counter_server.py: /api/counter/candidates imports from JSONL
  -> User reviews + confirms in knowledge base panel
  -> CONFIRMED counter-examples -> Learning / Rule updates
```

**Key principle:** Hook only produces CANDIDATE status. CONFIRMED requires human or skill-based confirmation.

## Auto-start server

Check if port 18720 is occupied. If not, start counter server in background:

```bash
python counter_server.py --no-browser &
```

Check method:
```bash
python -c "import socket; s=socket.socket(); s.settimeout(0.3); r=s.connect_ex(('127.0.0.1',18720)); s.close(); print('running' if r==0 else 'stopped')"
```

## Trigger methods

- **Auto**: UserPromptSubmit hook detects correction signals -> writes CANDIDATE via 18720 API
- `/反例 <description>`: Manual registration, appends to counter inbox
- `/反例` (no args): Interactive guided entry

## Loop prevention rules (MUST follow)

### 1. Dedup check
Query existing inbox items via 18720 API before writing:
```bash
curl -s "http://127.0.0.1:18720/api/counter" | python -c "
import sys,json
data = json.load(sys.stdin)
existing = [i.get('text','')[:60] for i in data.get('items',[])]
new_text = '<extracted error description>[:60]'
if any(new_text in e or e in new_text for e in existing):
    print('DUPLICATE')
"
```
If output is `DUPLICATE`, skip writing.

### 2. Same-session cooldown
Auto-capture triggers at most 3 times per session. Manual `/反例` is unlimited.

### 3. Write via counter server (18720), NOT Minta API (8772)
Structured append:
```bash
curl -s -X POST "http://127.0.0.1:18720/api/counter/append" \
  -H "Content-Type: application/json" \
  -d '{"text":"<description>","confidence":0.9,"tags":["<tag>"]}'
```

The old 8772 endpoint is DEPRECATED for counter-capture. Do NOT use `http://127.0.0.1:8772/api/inbox/append`.

## Auto-capture rules (Hook-driven, R5C.P1)

The `hooks/counter_capture.py` module handles automatic detection. Signal patterns:

| Signal | Keywords | Confidence |
|--------|----------|------------|
| Direct negation | "wrong", "incorrect", "not right", "mistake" | 0.75 |
| Rhetorical correction | "why didn't you", "you should first", "should have first" | 0.70 |
| Contrast correction | "I wanted X not Y", "should be X" | 0.80 |
| Redo instruction | "redo", "do it again", "rewrite", "fix it" | 0.65 |
| General dissatisfaction | "unsatisfied", "not good", "don't do that" | 0.55 |

Config-driven endpoint resolution (env -> ~/.minta/config.json -> default 18720):
```json
{
  "counter_capture": {
    "enabled": true,
    "endpoint": "http://127.0.0.1:18720/api/counter/append",
    "fallback_queue": "~/.minta/counter/candidate-queue.jsonl",
    "timeout_ms": 300
  }
}
```

## Manual registration `/反例 <description>`

Writes directly to counter inbox via 18720 API. Auto-infers tags. Confidence defaults to 0.9.
Notify user: `📥 Registered to inbox`

## Interactive guidance `/反例` (no args)

Ask user three questions:
1. What did Claude do wrong?
2. What should the correct behavior be?
3. Why? (optional)

After collecting, write to inbox. Confidence defaults to 0.9.

## Inbox location

`Minta-next/.remember/counter-inbox.md`

## Management

- `/反例面板` -- Open knowledge base management panel (with server)
- `/反例整理` -- Command-line batch archive to feedback_counter-examples.md
- `GET /api/counter/candidates` -- Import from JSONL fallback queue

## Candidate confirmation workflow

1. Candidate enters inbox with status `pending`, source `user_prompt_submit` or `manual`
2. User (or counter-capture Skill) reviews candidate
3. Confirm -> archive to feedback file, create ContextObject with `source: "counter_example"`
4. Reject -> discard with reason tag

## Error categories

| Category | Description |
|----------|-------------|
| FACTUAL_ERROR | Factually incorrect statement |
| CONCEPT_CONFUSION | Confused two distinct concepts |
| STATE_SEMANTICS_ERROR | Wrong assumption about system state |
| USER_PREFERENCE_CORRECTION | User preference, not system error |
| PROJECT_CONTEXT_ERROR | Wrong project context/assumptions |
| PATH_OR_RUNTIME_ERROR | Wrong path, port, or runtime info |
| OVERCLAIM | Claimed something that wasn't true |
| MISSING_CONSTRAINT | User adds missing constraint |
