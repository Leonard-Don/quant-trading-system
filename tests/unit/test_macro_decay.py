from backend.app.api.v1.endpoints.macro_decay import build_structural_decay_radar


def test_structural_decay_radar_escalates_when_people_governance_and_evidence_align():
    overview = {
        "people_layer_summary": {
            "label": "fragile",
            "summary": "人事脆弱度均值 0.66，技术权威被稀释。",
            "avg_fragility_score": 0.66,
            "fragile_company_count": 2,
            "supportive_company_count": 0,
            "watchlist": [
                {
                    "symbol": "BABA",
                    "company_name": "阿里巴巴",
                    "people_fragility_score": 0.82,
                    "summary": "招聘稀释度高企。",
                }
            ],
        },
        "department_chaos_summary": {
            "label": "chaotic",
            "summary": "2 个政策主体进入高混乱区。",
            "avg_chaos_score": 0.61,
            "department_count": 3,
            "chaotic_department_count": 2,
            "top_departments": [
                {
                    "department": "ndrc",
                    "department_label": "发改委",
                    "chaos_score": 0.72,
                    "reason": "方向反复 3 次",
                }
            ],
        },
        "evidence_summary": {
            "conflict_level": "high",
            "policy_source_health_summary": {"label": "fragile"},
        },
        "input_reliability_summary": {
            "label": "fragile",
            "summary": "政策源脆弱，证据链断裂。",
        },
        "factors": [
            {"name": "tech_dilution", "z_score": 1.7, "value": 0.72, "confidence": 0.8},
            {"name": "baseload_mismatch", "z_score": 1.5, "value": 0.58, "confidence": 0.7},
            {"name": "bureaucratic_friction", "z_score": 1.6, "value": 0.64, "confidence": 0.7},
        ],
    }

    radar = build_structural_decay_radar(overview)

    assert radar["label"] == "decay_alert"
    assert radar["score"] >= 0.68
    assert radar["critical_axis_count"] >= 3
    assert radar["focus_companies"][0]["symbol"] == "BABA"
    assert radar["focus_departments"][0]["department"] == "ndrc"
    assert radar["top_signals"][0]["score"] >= radar["top_signals"][-1]["score"]


def test_structural_decay_radar_stays_stable_when_signals_are_calm():
    radar = build_structural_decay_radar(
        {
            "people_layer_summary": {
                "label": "stable",
                "summary": "人的维度稳定。",
                "avg_fragility_score": 0.16,
                "watchlist": [{"symbol": "NVDA", "people_fragility_score": 0.2}],
            },
            "department_chaos_summary": {
                "label": "stable",
                "summary": "政策主体稳定。",
                "avg_chaos_score": 0.12,
                "department_count": 2,
                "chaotic_department_count": 0,
                "top_departments": [],
            },
            "evidence_summary": {
                "conflict_level": "none",
                "policy_source_health_summary": {"label": "healthy"},
            },
            "input_reliability_summary": {"label": "robust", "summary": "证据链稳定。"},
            "factors": [{"name": "tech_dilution", "z_score": 0.2, "value": 0.1, "confidence": 0.8}],
        }
    )

    assert radar["label"] == "stable"
    assert radar["score"] < 0.44
    assert all(axis["status"] != "critical" for axis in radar["axes"])
