# Meeting-to-Action

**[llm-tools](https://swapnanilsaha.com) suite by Swapnanil Saha**

Enterprise meetings generate decisions and commitments that get buried in unstructured notes. Action items go unassigned, deadlines stay ambiguous, follow-up emails take 20 minutes to write, and commitments slip across weeks without anyone noticing. **Meeting-to-Action** extracts structure from chaos — and tracks it over time.

Paste in a raw transcript (Zoom, Teams, or Meet format) — get back decisions, action items with owners and deadlines, risk flags, a type-aware follow-up email, cross-meeting commitment tracking, and a weekly digest. Normalize messy transcripts automatically. Push structured output directly to a Notion database.

---

## Features

| # | Feature | What it does |
|---|---------|--------------|
| 1 | **Transcript Normalization** | Strips Zoom `[00:02:14]`, Teams `-->`, Meet `(00:02)` timestamps. Normalizes email speaker labels and ALL_CAPS names. Detects source format. |
| 2 | **Meeting Type Detection** | Classifies each meeting as standup, retrospective, exec\_review, sprint\_planning, incident\_review, and more — with a confidence score. |
| 3 | **Batch Processing** | Process an entire directory of transcripts in one command. Failures are isolated — one bad file doesn't stop the rest. |
| 4 | **Commitment Tracker** | Compare action items across meetings. Flag missed commitments with severity, count meetings elapsed, and identify the highest-risk owner. |
| 5 | **Weekly Digest** | Rule-based aggregation across all meetings: open items by owner, escalated risks (deduplicated), carry-forward items, and an LLM-generated digest email. |
| 6 | **Notion Integration** | Push structured meeting output directly to a Notion database. Requires `NOTION_API_KEY` and `NOTION_DATABASE_ID`. |

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
pip install -r requirements.txt

# Single transcript
python main.py run --file examples/sample_transcript_1.txt

# Skip normalization (already clean)
python main.py run --file transcript.txt --raw

# Push to Notion after extraction
python main.py run --file transcript.txt --push-notion

# Batch: process entire directory
python main.py batch --dir ./transcripts/

# Batch with weekly digest
python main.py batch --dir ./transcripts/ --digest

# Weekly digest from multiple extracted JSON files
python main.py digest meeting1.json meeting2.json meeting3.json

# Commitment tracker across meeting sessions
python main.py track-commitments session1.json session2.json session3.json
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/extract` | Extract from transcript text |
| `POST` | `/extract/file` | Extract from uploaded `.txt` file |
| `POST` | `/extract/batch` | Batch extract from multiple transcripts |
| `POST` | `/digest` | Build weekly digest from meeting outputs |
| `POST` | `/track-commitments` | Track missed commitments across sessions |
| `POST` | `/push-to-notion` | Push a meeting output to Notion |

---

## Sample Input → Output

**Input** (raw Zoom transcript):
```
[00:02:14] Alice: Good morning. Still blocked on Redis — 450ms latency in auth.
[00:03:01] Bob: I'll own the fix by Wednesday.
[00:03:20] Charlie: Deployment needs Priya's approval before we can move.
```

**Output** (standup format):
```
## Meeting Type: standup (confidence: 0.94)

## Action Items
| Task | Owner | Deadline | Priority |
|------|-------|----------|----------|
| Fix Redis latency on auth service | Bob | Wednesday EOD | High |
| Get deployment approval from Priya | Charlie | Today | High |

## Risk Flags
[CRITICAL] Redis auth service latency at 450ms — blocking API consumers.

## Follow-up (standup format)
🔴 Blockers
- Redis latency spike (Bob owns fix by Wednesday)
- Deployment approval pending (Priya)
🔄 In Progress
- Auth service performance investigation
✅ Done
- Sprint planning scheduled
```

---

## Output Schema

```json
{
  "meeting_title": "string | null",
  "date": "string | null",
  "participants": ["string"],
  "meeting_type": "standup | retrospective | exec_review | sprint_planning | ...",
  "meeting_type_confidence": 0.94,
  "decisions": ["string"],
  "action_items": [
    { "task": "string", "owner": "string | null", "deadline": "string | null", "priority": "high|medium|low" }
  ],
  "open_questions": ["string"],
  "risk_flags": [
    { "description": "string", "severity": "critical|moderate|low" }
  ],
  "formatted_follow_up": "string",
  "summary": "string"
}
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest
# 63 tests, 0 failures
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key. |
| `MODEL` | `claude-sonnet-4-6` | Claude model to use. |
| `MAX_TOKENS` | `2048` | Max tokens per extraction. |
| `NOTION_API_KEY` | — | Required only for Notion integration. |
| `NOTION_DATABASE_ID` | — | Required only for Notion integration. |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |

---

## Live Demo

[swapnanil.github.io/meeting-to-action](https://swapnanil.github.io/meeting-to-action)

---

Built by **Swapnanil Saha** — [swapnanilsaha.com](https://swapnanilsaha.com)
