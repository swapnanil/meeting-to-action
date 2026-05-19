from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

load_dotenv()

from agent.extractor import extract_meeting_output
from agent.models import (
    BatchResult,
    CommitmentTrackerResult,
    MeetingOutput,
    WeeklyDigest,
)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Meeting-to-Action API",
    description="Transform raw meeting transcripts into structured, actionable output.",
    version="2.0.0",
)


class ExtractRequest(BaseModel):
    transcript: str
    format: str = "json"
    skip_normalize: bool = False


class BatchTranscript(BaseModel):
    filename: str
    text: str


class BatchRequest(BaseModel):
    transcripts: list[BatchTranscript]
    generate_digest: bool = False
    skip_normalize: bool = False


class DigestRequest(BaseModel):
    sessions: list[MeetingOutput]
    week_label: str = ""


class CommitmentRequest(BaseModel):
    sessions: list[MeetingOutput]


class NotionPushRequest(BaseModel):
    transcript: str
    skip_normalize: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": os.environ.get("MODEL", "claude-sonnet-4-6"), "version": "2.0.0"}


@app.post("/extract", response_model=MeetingOutput)
def extract(request: ExtractRequest) -> MeetingOutput:
    try:
        return extract_meeting_output(request.transcript, skip_normalize=request.skip_normalize)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@app.post("/extract/file", response_model=MeetingOutput)
async def extract_file(file: UploadFile = File(...), skip_normalize: bool = False) -> MeetingOutput:
    raw = await file.read()
    try:
        transcript = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded text.")
    try:
        return extract_meeting_output(transcript, skip_normalize=skip_normalize)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@app.post("/extract/batch", response_model=BatchResult)
def extract_batch(request: BatchRequest) -> BatchResult:
    from agent.batch import process_batch
    try:
        transcripts = [{"filename": t.filename, "text": t.text} for t in request.transcripts]
        return process_batch(
            transcripts,
            generate_digest=request.generate_digest,
            skip_normalize=request.skip_normalize,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {e}")


@app.post("/digest", response_model=WeeklyDigest)
def digest(request: DigestRequest) -> WeeklyDigest:
    from agent.digest import build_digest
    try:
        return build_digest(request.sessions, week_label=request.week_label)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Digest generation failed: {e}")


@app.post("/track-commitments", response_model=CommitmentTrackerResult)
def track_commitments(request: CommitmentRequest) -> CommitmentTrackerResult:
    from agent.commitment_tracker import track_commitments as _track
    try:
        return _track(request.sessions)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commitment tracking failed: {e}")


@app.post("/extract/notion")
def extract_and_push_notion(request: NotionPushRequest) -> dict:
    from agent.notion import push_to_notion
    try:
        output = extract_meeting_output(request.transcript, skip_normalize=request.skip_normalize)
        result = push_to_notion(output)
        return {"meeting_output": output.model_dump(), **result}
    except (EnvironmentError, ImportError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notion push failed: {e}")


@app.post("/push-to-notion")
def push_notion(output: MeetingOutput) -> dict:
    from agent.notion import push_to_notion
    try:
        return push_to_notion(output)
    except (EnvironmentError, ImportError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
