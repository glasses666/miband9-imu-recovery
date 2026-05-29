import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

SENSITIVE_RE = re.compile(r"(auth|token|password|secret|key)", re.IGNORECASE)


@dataclass
class Result:
    ok: bool
    command: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return redact(payload)

    def to_json(self, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2 if pretty else None, sort_keys=True)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if SENSITIVE_RE.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
