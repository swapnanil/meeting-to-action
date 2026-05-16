import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

load_dotenv()

from agent.extractor import extract_meeting_output
from agent.models import MeetingOutput

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Meeting-to-Action API",
    description="Transform raw meeting transcripts into structured, actionable output.",
    version="1.0.0",
)


class ExtractRequest(BaseModel):
    transcript: str
    format: str = "json"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": os.environ.get("MODEL", "claude-sonnet-4-6")}


@app.post("/extract", response_model=MeetingOutput)
def extract(request: ExtractRequest) -> MeetingOutput:
    try:
        return extract_meeting_output(request.transcript)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@app.post("/extract/file", response_model=MeetingOutput)
async def extract_file(file: UploadFile = File(...)) -> MeetingOutput:
    raw = await file.read()
    try:
        transcript = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded text.")
    try:
        return extract_meeting_output(transcript)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")
