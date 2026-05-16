# Meeting-to-Action

**[llm-tools](https://swapnanilsaha.com) suite by Swapnanil Saha**

Enterprise meetings generate decisions and commitments that get lost in unstructured notes. Action items go unassigned, deadlines are ambiguous, and follow-up emails take 20 minutes to write. **Meeting-to-Action** extracts structure from chaos in under 10 seconds.

Paste in a raw transcript or meeting notes — get back decisions, action items with owners and deadlines, open questions, risk flags, and a ready-to-send follow-up email.

---

## Quick Start (Docker)

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
docker-compose up api         # start the REST API on :8000
curl -s http://localhost:8000/health
```

---

## CLI Usage

```bash
# Install dependencies
pip install -r requirements.txt

# From a file
python main.py run --file examples/sample_transcript_1.txt

# From stdin
cat transcript.txt | python main.py run --stdin

# Output formats: json | markdown (default) | email-only
python main.py run --file examples/sample_transcript_1.txt --format json
python main.py run --file examples/sample_transcript_1.txt --format email-only

# Save to file
python main.py run --file examples/sample_transcript_1.txt --format json --output results/meeting.json
```

**Via Docker:**
```bash
docker-compose run --rm cli run --file examples/sample_transcript_1.txt
```

---

## API Usage

### Health check
```bash
curl http://localhost:8000/health
# {"status":"ok","model":"claude-sonnet-4-6"}
```

### Extract from text
```bash
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Alice: We agreed to ship by Friday. Bob will handle the release."}'
```

### Extract from file upload
```bash
curl -X POST http://localhost:8000/extract/file \
  -F "file=@examples/sample_transcript_1.txt"
```

---

## Sample Input → Output

**Input** (`examples/sample_transcript_1.txt`):
```
Alice: Good morning everyone. The Redis latency has been really problematic.
Bob: I've been seeing 200ms+ response times. It might be connection pool exhaustion.
Alice: Bob, can you own this and get it sorted by Wednesday?
Bob: Sure, I'll dig in today.
...
```

**Output** (markdown format):
```
# Engineering Standup
**Date:** 2026-05-17
**Participants:** Alice Chen, Bob Patel, Charlie Nwosu

## Executive Summary
The team aligned on Redis fix ownership and unblocking the stalled deployment...

## Action Items
| Task | Owner | Deadline | Priority |
|------|-------|----------|----------|
| Fix Redis latency on auth service | Bob Patel | Wednesday EOD | High |
| Deliver rollback plan doc | Bob Patel | Today EOD | High |
| Escalate INF-2284 to Priya | Charlie Nwosu | This morning | High |

## Risk Flags
**[CRITICAL]** Redis auth service latency spiking to 450ms — indirectly blocking API team.
**[MODERATE]** Deployment blocked on infrastructure board sign-off — Q2 release at risk.

## Follow-up Email
---
Team,

Thanks for a productive standup. Here's a summary of what we aligned on...
---
```

Full example JSON output: [`examples/sample_output.json`](examples/sample_output.json)

---

## Output Schema

```json
{
  "meeting_title": "string | null",
  "date": "string | null",
  "participants": ["string"],
  "decisions": ["string"],
  "action_items": [
    { "task": "string", "owner": "string | null", "deadline": "string | null", "priority": "high|medium|low" }
  ],
  "open_questions": ["string"],
  "risk_flags": [
    { "description": "string", "severity": "critical|moderate|low" }
  ],
  "follow_up_email": "string",
  "summary": "string"
}
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key. |
| `MODEL` | `claude-sonnet-4-6` | Claude model to use. |
| `MAX_TOKENS` | `2048` | Max tokens in Claude's response. |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |

---

## Live Demo

_Link to be added._

---

Built by **Swapnanil Saha** — [swapnanilsaha.com](https://swapnanilsaha.com)
