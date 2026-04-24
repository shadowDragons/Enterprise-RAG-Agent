from app.core.review_rules import default_review_rules, evaluate_review_hit


def test_evaluate_review_hit_uses_rule_priority() -> None:
    rules = [
        {
            "rule_id": "rule-b",
            "rule_name": "次优先规则",
            "category": "分类B",
            "severity": "medium",
            "priority": 200,
            "enabled": True,
            "match_mode": "contains_any",
            "keywords": ["起诉"],
            "regex_pattern": "",
        },
        {
            "rule_id": "rule-a",
            "rule_name": "高优先规则",
            "category": "分类A",
            "severity": "critical",
            "priority": 100,
            "enabled": True,
            "match_mode": "contains_any",
            "keywords": ["起诉", "仲裁"],
            "regex_pattern": "",
        },
    ]

    hit = evaluate_review_hit("如果我要起诉供应商，应该怎么做？", rules)

    assert hit is not None
    assert hit.rule_id == "rule-a"
    assert hit.rule_name == "高优先规则"
    assert hit.category == "分类A"
    assert hit.severity == "critical"
    assert "起诉" in hit.reason


def test_evaluate_review_hit_supports_contains_all() -> None:
    rules = [
        {
            "rule_id": "rule-all",
            "rule_name": "组合命中规则",
            "category": "合规",
            "severity": "high",
            "priority": 100,
            "enabled": True,
            "match_mode": "contains_all",
            "keywords": ["供应商", "赔偿"],
            "regex_pattern": "",
        }
    ]

    assert evaluate_review_hit("供应商条款需要复核。", rules) is None

    hit = evaluate_review_hit("供应商违约后如何赔偿？", rules)

    assert hit is not None
    assert hit.match_mode == "contains_all"
    assert hit.matched_keywords == ("供应商", "赔偿")
    assert "同时命中关键词" in hit.reason


def test_evaluate_review_hit_supports_regex_pattern() -> None:
    rules = [
        {
            "rule_id": "rule-regex",
            "rule_name": "个人信息识别",
            "category": "隐私",
            "severity": "critical",
            "priority": 100,
            "enabled": True,
            "match_mode": "regex",
            "keywords": [],
            "regex_pattern": r"(身份证号?|手机号)",
        }
    ]

    hit = evaluate_review_hit("员工身份证号需要怎么脱敏？", rules)

    assert hit is not None
    assert hit.match_mode == "regex"
    assert hit.regex_pattern == r"(身份证号?|手机号)"
    assert hit.matched_fragment == "身份证号"
    assert "命中模式" in hit.reason


def test_default_review_rules_cover_expected_categories() -> None:
    categories = {item["category"] for item in default_review_rules()}

    assert {"法律", "隐私", "医疗", "投资"} <= categories
