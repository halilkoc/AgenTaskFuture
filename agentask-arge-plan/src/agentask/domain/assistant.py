"""İşlem Asistanı kural motoru (modelsiz) ve model çıktısı doğrulayıcı.

Talep yalnız etkin yayındaki onaylı işlemler arasından seçim yapabilir; talep metni işlem kümesini
genişletemez
(prompt injection yüzeyi: yalnız seçim + parametre değeri). Parametre uydurulmaz; bulunamayan sorulur.
Eşit puanlı
işlemler arasında seçim yapılmaz. Model çıktısı yalnız {operation_id, arguments} şemasıdır ve enum ile
doğrulanır.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agentask.domain.sensitive import is_sensitive, scan
from agentask.domain.targeting import normalize_name

_STOP = {
    "ve",
    "ile",
    "bir",
    "bu",
    "su",
    "icin",
    "olarak",
    "lutfen",
    "numarasini",
    "numarasi",
    "gir",
    "yaz",
    "ekle",
    "yap",
    "et",
    "da",
    "de",
    "mi",
    "ne",
}
_QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{1,500})[\"'“”‘’]")
_ID_LIKE = re.compile(r"(?<![\w-])([A-Za-z]{1,4}-\d{1,12}|\d{1,30})(?![\w-])")


class CatalogParam(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    title: str
    max_length: int
    is_choice: bool = False  # bir seçim adımını besliyor
    multiple: bool = False  # satır başına bir seçim üyesi
    file: bool = False  # yetkili depoya yüklenen dosya
    choices: list[str] | None = None  # None: liste sabit değil; çalışma anında doğrulanır


class CatalogOperation(BaseModel):
    model_config = ConfigDict(frozen=True)
    release_id: str
    operation_id: str
    revision: int
    content_hash: str
    title: str
    intent_phrases: list[str]
    parameters: list[CatalogParam]
    migration_required: bool = False  # ekran tanımı olmayan eski yayın; çalıştırılmaz


@dataclass(frozen=True, slots=True)
class Candidate:
    operation_id: str
    title: str
    score: int


@dataclass
class Interpretation:
    status: Literal["matched", "needs_clarification", "no_match"]
    operation_id: str | None
    release_id: str | None
    arguments: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    provenance: Literal["rule_generated", "model_suggested"] = "rule_generated"
    explanation: str = ""
    sensitive: list[str] = field(default_factory=list)  # yalnız şüphe türleri; değer asla tutulmaz


def _tokens(text: str) -> set[str]:
    words = re.split(r"[^\w]+", normalize_name(text))
    return {w for w in words if len(w) >= 2 and w not in _STOP}


def _overlap(prompt: set[str], phrase_tokens: set[str]) -> int:
    hits = 0
    for t in phrase_tokens:
        if any(
            w == t or (len(t) >= 4 and (w.startswith(t[:5]) or t.startswith(w[:5])) and len(w) >= 4)
            for w in prompt
        ):
            hits += 1
    return hits


def _score(prompt: set[str], op: CatalogOperation) -> int:
    phrases = [op.title, *op.intent_phrases]
    return max(_overlap(prompt, _tokens(p)) for p in phrases)


def extract_arguments(prompt: str, op: CatalogOperation) -> tuple[dict[str, str], list[str], list[str]]:
    """(bulunan, eksik, geçersiz) döner. Değerler talepten birebir alınır (baştaki sıfırlar korunur)."""
    found: dict[str, str] = {}
    used: set[str] = set()
    # Hassas olduğundan şüphelenilen değerler hiçbir parametreye bağlanmaz (kullanıcıdan güvenli yol istenir).
    quoted = [q for q in (m.group(1).strip() for m in _QUOTED.finditer(prompt)) if not is_sensitive(q)]
    scrubbed = _QUOTED.sub(" ", prompt)
    for finding in reversed(scan(scrubbed)):
        scrubbed = scrubbed[: finding.start] + " " + scrubbed[finding.end :]
    ids = [m.group(1) for m in _ID_LIKE.finditer(scrubbed)]
    for param in op.parameters:
        anchor = re.compile(re.escape(param.title) + r"\w*\s*(?::|=|olarak)?\s*([^\s,;]+)", re.IGNORECASE)
        m = anchor.search(scrubbed)
        if m and _ID_LIKE.fullmatch(m.group(1)):
            found[param.name] = m.group(1)
            used.add(m.group(1))
    remaining = [p for p in op.parameters if p.name not in found]
    free_quoted = [q for q in quoted if q not in used]
    free_ids = [i for i in ids if i not in used]
    if len(remaining) == 1:
        pool = free_quoted if free_quoted else free_ids
        if len(pool) == 1:
            found[remaining[0].name] = pool[0]
    missing = [p.name for p in op.parameters if p.name not in found]
    invalid = [p.name for p in op.parameters if p.name in found and len(found[p.name]) > p.max_length]
    for name in invalid:
        found.pop(name)
    return found, missing, invalid


def interpret_rules(prompt: str, operations: list[CatalogOperation]) -> Interpretation:
    words = _tokens(prompt)
    scored = sorted(((_score(words, op), op) for op in operations), key=lambda x: -x[0])
    candidates = [Candidate(op.operation_id, op.title, s) for s, op in scored if s >= 1][:5]
    if not candidates:
        return Interpretation("no_match", None, None, explanation="Talep onaylı bir işlemle eşleşmedi.")
    if len(candidates) > 1 and candidates[0].score == candidates[1].score:
        return Interpretation(
            "needs_clarification",
            None,
            None,
            candidates=candidates,
            explanation="Talep birden fazla işlemle aynı ölçüde eşleşti; hangisi kastedildi?",
        )
    if candidates[0].score < 2:
        return Interpretation(
            "needs_clarification",
            None,
            None,
            candidates=candidates,
            explanation="Eşleşme zayıf; işlemi seçerek onaylayın.",
        )
    op = next(o for o in operations if o.operation_id == candidates[0].operation_id)
    args, missing, invalid = extract_arguments(prompt, op)
    status: Literal["matched", "needs_clarification"] = (
        "matched" if not missing and not invalid else "needs_clarification"
    )
    explanation = (
        "İşlem ve parametreler bulundu." if status == "matched" else "Eksik veya geçersiz parametre var."
    )
    return Interpretation(
        status,
        op.operation_id,
        op.release_id,
        args,
        missing,
        invalid,
        candidates[:3],
        explanation=explanation,
    )


class ModelOutputRejected(ValueError):
    pass


class BudgetExceeded(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSuggestion:
    operation_id: str
    arguments: dict[str, str]


def choice_schema(operations: list[CatalogOperation]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["operation_id", "arguments"],
        "properties": {
            "operation_id": {"type": "string", "enum": [o.operation_id for o in operations]},
            "arguments": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }


def validate_model_choice(raw: Any, operations: list[CatalogOperation]) -> ModelSuggestion:
    """Şemaya uygunluk semantik doğruluk değildir; yalnız izinli işlem/argüman kümesine sınırlar."""
    if not isinstance(raw, dict) or set(raw) != {"operation_id", "arguments"}:
        raise ModelOutputRejected("schema")
    op_id, args = raw["operation_id"], raw["arguments"]
    if (
        not isinstance(op_id, str)
        or not isinstance(args, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in args.items())
    ):
        raise ModelOutputRejected("schema")
    op = next((o for o in operations if o.operation_id == op_id), None)
    if op is None:
        raise ModelOutputRejected("unknown_operation")
    allowed = {p.name: p for p in op.parameters}
    for name, value in args.items():
        if name not in allowed:
            raise ModelOutputRejected("unknown_argument")
        if len(value) > allowed[name].max_length:
            raise ModelOutputRejected("argument_too_long")
    return ModelSuggestion(op_id, dict(args))


# F: modelin önerebileceği sıralı plan uzunluğu (ürün sınırı; dağıtıma bağlı ayar değildir).
MAX_PLAN_OPERATIONS = 5


def plan_schema(operations: list[CatalogOperation]) -> dict[str, Any]:
    """Çok adımlı plan önerisi: yalnız yayındaki işlemlerin sıralı listesi (koşul/döngü/serbest kod yok)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["steps"],
        "properties": {
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_PLAN_OPERATIONS,
                "items": choice_schema(operations),
            }
        },
    }


def validate_model_plan(raw: Any, operations: list[CatalogOperation], prompt: str) -> list[ModelSuggestion]:
    """Model planını yalnız izinli işlem/argüman kümesine sınırlar. Talepte geçmeyen argüman değeri atılır
    (uydurma engeli); eksik kalan değerler kullanıcıdan istenir. Güven puanı veya açıklama kabul edilmez."""
    if not isinstance(raw, dict) or set(raw) != {"steps"} or not isinstance(raw["steps"], list):
        raise ModelOutputRejected("schema")
    steps = raw["steps"]
    if not 1 <= len(steps) <= MAX_PLAN_OPERATIONS:
        raise ModelOutputRejected("plan_length")
    out: list[ModelSuggestion] = []
    for item in steps:
        choice = validate_model_choice(item, operations)
        out.append(
            ModelSuggestion(
                choice.operation_id, {k: v for k, v in choice.arguments.items() if v and v in prompt}
            )
        )
    return out


def estimate_tokens(text: str) -> int:
    """Tokenizer yok: muhafazakâr tahmin (3 karakter ≈ 1 token). Kesin değildir."""
    return math.ceil(len(text) / 3)


def check_budget(text: str, max_input_tokens: int) -> int:
    tokens = estimate_tokens(text)
    if tokens > max_input_tokens:
        raise BudgetExceeded(f"input_tokens:{tokens}>{max_input_tokens}")
    return tokens
