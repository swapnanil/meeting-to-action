from __future__ import annotations

import logging
import time
from pathlib import Path

from agent.extractor import extract_meeting_output
from agent.models import BatchFileResult, BatchResult, MeetingOutput

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".text"}


def process_batch(
    transcripts: list[dict],  # [{"filename": str, "text": str}]
    generate_digest: bool = False,
    skip_normalize: bool = False,
) -> BatchResult:
    results: list[BatchFileResult] = []

    for item in transcripts:
        filename = item.get("filename", "unknown")
        text = item.get("text", "")
        t0 = time.monotonic()
        try:
            output = extract_meeting_output(text, skip_normalize=skip_normalize)
            results.append(BatchFileResult(
                filename=filename,
                status="success",
                output=output,
                error=None,
                duration_seconds=round(time.monotonic() - t0, 2),
            ))
        except Exception as e:
            logger.warning("Batch: failed to process %s: %s", filename, e)
            results.append(BatchFileResult(
                filename=filename,
                status="failed",
                output=None,
                error=str(e),
                duration_seconds=round(time.monotonic() - t0, 2),
            ))

    succeeded = sum(1 for r in results if r.status == "success")

    digest = None
    if generate_digest:
        from agent.digest import build_digest
        successful_outputs = [r.output for r in results if r.output is not None]
        if successful_outputs:
            digest = build_digest(successful_outputs)

    return BatchResult(
        total_files=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
        digest=digest,
    )


def process_directory(
    directory: Path,
    generate_digest: bool = False,
    skip_normalize: bool = False,
) -> BatchResult:
    files = sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    transcripts = [
        {"filename": f.name, "text": f.read_text(encoding="utf-8")}
        for f in files
    ]
    return process_batch(transcripts, generate_digest=generate_digest, skip_normalize=skip_normalize)
