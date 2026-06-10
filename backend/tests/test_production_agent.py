import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.agents.production_agent import ProductionAgent


def make_fact(**overrides):
    data = {
        "id": str(uuid.uuid4()),
        "brand_id": str(uuid.uuid4()),
        "fact_type": "qualification",
        "value": "民用无人驾驶航空器运营合格证",
        "public_wording": "具备民用无人驾驶航空器运营合格证",
        "fact_scope": "public",
        "status": "confirmed",
        "risk_level": "low",
        "valid_until": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_parse_separated_json_metadata_removes_title_from_body():
    raw = (
        json.dumps(
            {
                "title_candidates": ["包头无人机培训怎么选"],
                "aida": {"attention": "开头"},
            },
            ensure_ascii=False,
        )
        + "\n---FULL_CONTENT---\n"
        + "# 包头无人机培训怎么选\n\n正文第一段，不应包含JSON。"
    )

    parsed = ProductionAgent.parse_llm_output(raw)

    assert parsed["title"] == "包头无人机培训怎么选"
    assert "title_candidates" not in parsed["body"]
    assert parsed["body"].startswith("正文第一段")


def test_parse_pure_json_uses_full_content_and_title_candidate():
    raw = json.dumps(
        {
            "title_candidates": ["CAAC执照报名流程"],
            "full_content": "CAAC执照报名流程\n\n这里是正文。",
        },
        ensure_ascii=False,
    )

    parsed = ProductionAgent.parse_llm_output(raw)

    assert parsed["title"] == "CAAC执照报名流程"
    assert parsed["body"] == "这里是正文。"


def test_parse_mixed_json_prefix_uses_trailing_body_and_strips_machine_sections():
    raw = (
        json.dumps(
            {
                "title_candidates": ["A clean title"],
                "aida": {
                    "attention": "Do not use this as body",
                    "interest": "This is only metadata",
                },
                "platform_notes": "Internal notes",
            },
            ensure_ascii=False,
        )
        + "\nActual article body starts here.\n\nSecond paragraph.\n\n"
        + "[FACT_REFS]\n- [qualification] Confirmed fact (ID: f1)\n\n"
        + "[COMPLIANCE_CHECK]\n- pass\n\n[END]"
    )

    parsed = ProductionAgent.parse_llm_output(raw)

    assert parsed["title"] == "A clean title"
    assert parsed["body"].startswith("Actual article body starts here.")
    assert "title_candidates" not in parsed["body"]
    assert "[FACT_REFS]" not in parsed["body"]
    assert "[COMPLIANCE_CHECK]" not in parsed["body"]
    assert "Do not use this as body" not in parsed["body"]
    assert "Confirmed fact" in parsed["fact_refs_raw"]
    assert "pass" in parsed["compliance_raw"]


def test_compliance_blocks_high_risk_claim_without_confirmed_reference():
    agent = ProductionAgent()
    issues = agent.check_compliance(
        "该机构拥有资质证书和多个客户案例，通过率表现稳定。",
        [],
    )

    assert any(issue["type"] == "resource_risk" for issue in issues)


def test_fact_references_only_use_public_confirmed_unexpired_facts():
    agent = ProductionAgent()
    valid_fact = make_fact()
    internal_fact = make_fact(fact_scope="internal")
    expired_fact = make_fact(valid_until=datetime.now(timezone.utc) - timedelta(days=1))

    refs = agent.generate_fact_references(
        "蒙霁具备民用无人驾驶航空器运营合格证。",
        [valid_fact, internal_fact, expired_fact],
    )

    assert [ref["fact_id"] for ref in refs] == [str(valid_fact.id)]


def test_article_prompt_includes_project_knowledge_assets_with_fact_boundary():
    agent = ProductionAgent()
    prompt = agent.generate_article_prompt(
        SimpleNamespace(content_type="brand_intro", layer="pool_layer", priority="medium"),
        [],
        platform="media",
        project=SimpleNamespace(name="知识资产测试项目", industry="professional_service", region="杭州", notes=""),
        brand=SimpleNamespace(brand_name="知识资产测试品牌", company_name="", description=""),
        knowledge_assets=[
            SimpleNamespace(
                title="客户故事片段",
                content="一位客户通过服务把交付周期从 14 天缩短到 7 天。",
                knowledge_layer="story",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope="project",
                source_type="case",
                source_url="https://example.com/story",
                tags="案例,交付",
            )
        ],
    )

    assert "项目知识资产" in prompt
    assert "客户故事片段" in prompt
    assert "交付周期从 14 天缩短到 7 天" in prompt
    assert "不能替代已确认品牌事实" in prompt


def test_article_prompt_includes_active_experience_skills():
    agent = ProductionAgent()
    prompt = agent.generate_article_prompt(
        SimpleNamespace(content_type="brand_intro", layer="pool_layer", priority="medium"),
        [],
        platform="media",
        project=SimpleNamespace(name="经验技能测试项目", industry="local_service", region="包头", notes=""),
        brand=SimpleNamespace(brand_name="经验技能测试品牌", company_name="", description=""),
        experience_skills=[
            SimpleNamespace(
                name="本地口语化写作",
                scope="project",
                trigger_scene="article_writing",
                skill_type="rule",
                content="文章要少一点AI味，多写本地场景和人的口吻。",
                confidence=0.82,
            )
        ],
    )

    assert "经验技能" in prompt
    assert "本地口语化写作" in prompt
    assert "多写本地场景和人的口吻" in prompt
