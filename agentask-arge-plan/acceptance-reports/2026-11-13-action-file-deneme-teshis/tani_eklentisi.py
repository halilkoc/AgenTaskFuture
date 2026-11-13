"""Teşhis: her adım denemesinin sonucu ve çalışma adımlarının durumları kaydedilir (değer yazılmaz)."""
import json, os
from agentask.application.services import designer as d
OUT = os.environ["DIAG_OUT"]
_trial = d.DesignerService.trial_step
async def trial_step(self, owner, draft_id, revision, step_id, *a, **kw):
    draft = await _trial(self, owner, draft_id, revision, step_id, *a, **kw)
    step = next(s for s in draft.steps if s.step_id == step_id)
    rec = {"adim": step.op, "deneme": step.trial.model_dump(mode="json", exclude={"at"}) if step.trial else None}
    try:
        run = self._runs.get(owner, step.trial.run_id) if step.trial else None
        if hasattr(run, "__await__"):
            run = await run
        if run is not None:
            rec["calisma"] = [{"op": s.command.get("op"), "durum": s.state.value, "hata": s.error_class, "mesaj": s.message} for s in run.steps]
    except Exception as exc:
        rec["calisma_okunamadi"] = type(exc).__name__
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return draft
d.DesignerService.trial_step = trial_step
