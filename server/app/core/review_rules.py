import re
from dataclasses import dataclass

_SEVERITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "严重",
}

_MATCH_MODE_CONTAINS_ANY = "contains_any"
_MATCH_MODE_CONTAINS_ALL = "contains_all"
_MATCH_MODE_REGEX = "regex"


@dataclass(frozen=True)
class ReviewRuleHit:
    rule_id: str
    rule_name: str
    category: str
    severity: str
    match_mode: str
    matched_keywords: tuple[str, ...] = ()
    regex_pattern: str = ""
    matched_fragment: str = ""

    @property
    def reason(self) -> str:
        severity_label = _SEVERITY_LABELS.get(self.severity, "高")
        rule_label = f"检测到 {self.category} {severity_label}风险规则“{self.rule_name}”"
        if self.match_mode == _MATCH_MODE_REGEX:
            detail = f"命中模式：{self.regex_pattern}"
            if self.matched_fragment:
                detail += f"（片段：{self.matched_fragment}）"
            return f"{rule_label}，{detail}"

        joined_keywords = "、".join(self.matched_keywords[:4])
        if self.match_mode == _MATCH_MODE_CONTAINS_ALL:
            return f"{rule_label}，同时命中关键词：{joined_keywords}"
        return f"{rule_label}，命中关键词：{joined_keywords}"


def default_review_rules() -> list[dict]:
    return [
        {
            "rule_id": "legal-risk",
            "rule_name": "法律风险识别",
            "category": "法律",
            "priority": 100,
            "severity": "critical",
            "enabled": True,
            "match_mode": "contains_any",
            "keywords": ["起诉", "仲裁", "诉讼", "违约", "赔偿", "律师", "违法"],
            "regex_pattern": "",
        },
        {
            "rule_id": "privacy-risk",
            "rule_name": "个人敏感信息识别",
            "category": "隐私",
            "priority": 150,
            "severity": "critical",
            "enabled": True,
            "match_mode": "regex",
            "keywords": [],
            "regex_pattern": r"(身份证号?|银行卡号?|手机号|手机号码|家庭住址|住址|隐私数据)",
        },
        {
            "rule_id": "medical-risk",
            "rule_name": "医疗风险识别",
            "category": "医疗",
            "priority": 200,
            "severity": "critical",
            "enabled": True,
            "match_mode": "contains_any",
            "keywords": ["诊断", "处方", "用药", "药量", "治疗", "症状", "怀孕"],
            "regex_pattern": "",
        },
        {
            "rule_id": "investment-risk",
            "rule_name": "投资风险识别",
            "category": "投资",
            "priority": 300,
            "severity": "high",
            "enabled": True,
            "match_mode": "contains_any",
            "keywords": ["投资", "理财", "股票", "基金", "买入", "卖出", "收益率", "贷款"],
            "regex_pattern": "",
        },
    ]


def evaluate_review_hit(question: str, rules: list[dict]) -> ReviewRuleHit | None:
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return None

    normalized_rules = sorted(
        [item for item in rules if item.get("enabled", True)],
        key=lambda item: _safe_priority(item.get("priority", 1000)),
    )
    for item in normalized_rules:
        match_mode = str(
            item.get("match_mode", _MATCH_MODE_CONTAINS_ANY)
        ).strip() or _MATCH_MODE_CONTAINS_ANY
        if match_mode == _MATCH_MODE_REGEX:
            regex_pattern = str(item.get("regex_pattern", "")).strip()
            if not regex_pattern:
                continue
            try:
                matched = re.search(regex_pattern, question, flags=re.IGNORECASE)
            except re.error:
                continue
            if matched is None:
                continue
            return ReviewRuleHit(
                rule_id=_normalize_rule_id(item),
                rule_name=_normalize_rule_name(item),
                category=_normalize_rule_category(item),
                severity=_normalize_rule_severity(item),
                match_mode=match_mode,
                regex_pattern=regex_pattern,
                matched_fragment=matched.group(0).strip(),
            )

        rule_keywords = _normalize_keywords(item.get("keywords", []))
        if not rule_keywords:
            continue
        matched_keywords = tuple(
            keyword
            for keyword, normalized_keyword in rule_keywords
            if normalized_keyword in normalized_question
        )
        if match_mode == _MATCH_MODE_CONTAINS_ALL and len(matched_keywords) != len(
            rule_keywords
        ):
            continue
        if not matched_keywords:
            continue
        return ReviewRuleHit(
            rule_id=_normalize_rule_id(item),
            rule_name=_normalize_rule_name(item),
            category=_normalize_rule_category(item),
            severity=_normalize_rule_severity(item),
            match_mode=match_mode,
            matched_keywords=matched_keywords,
        )
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _normalize_keywords(keywords: list[str]) -> list[tuple[str, str]]:
    normalized_items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for keyword in keywords:
        display_keyword = str(keyword).strip()
        normalized_keyword = _normalize_text(display_keyword)
        if not normalized_keyword or normalized_keyword in seen:
            continue
        normalized_items.append((display_keyword, normalized_keyword))
        seen.add(normalized_keyword)
    return normalized_items


def _normalize_rule_id(item: dict) -> str:
    return str(item.get("rule_id", "")).strip() or "review-rule"


def _normalize_rule_name(item: dict) -> str:
    return str(item.get("rule_name", "")).strip() or "未命名规则"


def _normalize_rule_category(item: dict) -> str:
    return str(item.get("category", "")).strip() or "未分类"


def _normalize_rule_severity(item: dict) -> str:
    severity = str(item.get("severity", "high")).strip().lower()
    if severity not in _SEVERITY_LABELS:
        return "high"
    return severity


def _safe_priority(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1000
