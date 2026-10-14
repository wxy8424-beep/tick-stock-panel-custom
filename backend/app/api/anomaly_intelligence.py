"""Read-only stored Intelligence queries; never aggregate or persist on GET."""
from fastapi import APIRouter, HTTPException, Path, Request

from app.services.anomaly_intelligence import AnomalyIntelligenceStore, read_event
from app.services.evidence_policy import EvidencePolicyResolver, EvidencePolicyStore

router = APIRouter(prefix="/api/anomalies", tags=["anomaly-intelligence"])


@router.get("/{event_id}/intelligence")
def intelligence(request: Request, event_id: str = Path(pattern=r"^[a-f0-9]{64}$")):
    repo = getattr(request.app.state, "repo", None)
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        raise HTTPException(503, "异动事件存储未初始化")
    try:
        event = read_event(data_dir, event_id)
        if event is None:
            raise HTTPException(404, "异动事件不存在")
        record = AnomalyIntelligenceStore(data_dir).get(event_id)
        if record is not None:
            return record.to_dict()
        resolved = EvidencePolicyResolver(EvidencePolicyStore(data_dir)).resolve(event)
        blocker = "intelligence_not_collected"
        state = "UNAVAILABLE"
        if resolved["status"] == "BLOCKED":
            state = "BLOCKED"
            blocker = "no_applicable_evidence_policy" if resolved["blocker"] == "no_matching_policy" else resolved["blocker"]
        section = {"status": "UNAVAILABLE", "blocker": "intelligence_not_collected"}
        factor = section
        if resolved["status"] == "READY" and "factors" not in (
                resolved["selection_rules"]["required_evidence"] + resolved["selection_rules"]["optional_evidence"]):
            factor = {"status": "NOT_SELECTED", "blocker": None, "total_score": None}
        return {"event_id": event_id, "status": state, "policy": None, "historical": section,
                "market": section, "factor": factor, "blockers": [blocker], "generated_at": None,
                "version": "anomaly-intelligence-v1"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "异动证据存储暂不可读") from None
