"""FastAPI backend for the Campus Customs multi-agent operations dashboard.

Run with one worker, so the in-memory run guards see every request. Either
from the backend folder (with the Homework 5 .venv active):

    uvicorn main:app --reload --port 8000

or from the Homework 5 folder:

    .venv/bin/uvicorn backend.main:app --port 8000

Routes
  GET  /api/health
  GET  /api/tickets                         A. tickets and persisted status
  GET  /api/tickets/{ticket_id}                ticket detail (MCP get_ticket_details)
  POST /api/tickets/{ticket_id}/run         B. start the Boss-led workflow in the background
  GET  /api/runs, /api/runs/{run_id}           run state and result
  GET  /api/events                          C. recent agent events from the audit trail
  GET  /api/proposals                          payment and purchase proposals
  POST /api/proposals/{proposal_id}/approve D. explicit human approval
  POST /api/proposals/{proposal_id}/decline    explicit human decline
  GET  /api/cash/checking                   E. current checking balance
  POST /api/reset                           F. restore the working database baseline

Nothing here sends email, contacts vendors or moves real money: the only
financial effect is an approved payment recorded in the local working database.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Literal

# Make the `backend` package importable when uvicorn loads this file as a
# top-level module (`uvicorn main:app` run from inside backend/).
_HW_ROOT = str(FilePath(__file__).resolve().parent.parent)
if _HW_ROOT not in sys.path:
    sys.path.insert(0, _HW_ROOT)

from fastapi import FastAPI, Path, Query, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend.config import MODEL_ID, WORKING_DB  # noqa: E402
from backend.mcp_client import MCP_TOOLSET  # noqa: E402
from backend.service import OperationsService, ServiceError  # noqa: E402

service = OperationsService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One MCP session for the server's lifetime. The database is never reset here.
    async with MCP_TOOLSET:
        yield


app = FastAPI(title="Campus Customs Operations API", version="1.0", lifespan=lifespan)
# Only the local Vite dev server may call the API from a browser. No
# credentials are used, and no wildcard origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(ServiceError)
async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                        content={"ok": False, "error": exc.code, "message": exc.message,
                                 **exc.extra})


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=80,
                             description="Name of the human operator approving.")
    confirm_amount: float = Field(ge=0, description="The proposal's amount, exactly as shown.")
    confirm_payee: str = Field(min_length=1, max_length=120,
                               description="The proposal's payee, exactly as shown.")


class DeclineRequest(BaseModel):
    declined_by: str = Field(min_length=1, max_length=80,
                             description="Name of the human operator declining.")
    reason: str = Field(default="", max_length=300)


class ResetRequest(BaseModel):
    confirm: Literal["RESET"] = Field(description='Must be "RESET" to confirm.')


TicketId = Path(gt=0, description="tickets.id")


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "model": MODEL_ID, "database": WORKING_DB,
            "active_runs": dict(service.active)}


@app.get("/api/tickets")
async def list_tickets() -> dict:
    return await service.list_tickets()


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int = TicketId) -> dict:
    return await service.ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int = TicketId) -> dict:
    record = await service.start_run(ticket_id)
    return {"ok": True, "status": "started", "run_id": record.run_id, "ticket_id": ticket_id,
            "run_url": f"/api/runs/{record.run_id}",
            "events_url": f"/api/events?run_id={record.run_id}"}


@app.get("/api/runs")
async def list_runs() -> dict:
    return {"runs": service.list_runs()}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    return service.get_run(run_id)


@app.get("/api/events")
async def events(
    ticket_id: int | None = Query(default=None, gt=0),
    run_id: str | None = Query(default=None, max_length=40),
    after: str | None = Query(default=None, max_length=40,
                              description="Return only events after this event_id (for polling)."),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return service.events(ticket_id=ticket_id, run_id=run_id, after=after, limit=limit)


@app.get("/api/proposals")
async def proposals(
    ticket_id: int | None = Query(default=None, gt=0),
    status: Literal["pending", "executed", "approved", "declined", "superseded"] | None = None,
) -> dict:
    return await service.proposals(ticket_id, status)


@app.post("/api/proposals/{proposal_id}/approve")
async def approve(body: ApprovalRequest, proposal_id: int = Path(gt=0)) -> dict:
    return await service.approve(proposal_id, body.approved_by, body.confirm_amount,
                                 body.confirm_payee)


@app.post("/api/proposals/{proposal_id}/decline")
async def decline(body: DeclineRequest, proposal_id: int = Path(gt=0)) -> dict:
    return await service.decline(proposal_id, body.declined_by, body.reason)


@app.get("/api/cash/checking")
async def checking_balance() -> dict:
    return await service.checking_balance()


@app.post("/api/reset")
async def reset(body: ResetRequest) -> dict:
    return await service.reset()
