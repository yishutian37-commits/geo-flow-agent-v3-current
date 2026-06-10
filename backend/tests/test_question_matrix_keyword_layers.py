from types import SimpleNamespace

from app.api.v1.endpoints.projects import (
    _build_template_groups,
    _coerce_question_groups,
)


def test_coerced_question_groups_keep_keyword_layer_and_asset_fields():
    groups = _coerce_question_groups(
        {
            "groups": [
                {
                    "layer": "verification_layer",
                    "intent_name": "资质核验",
                    "representative_question": "这家公司有哪些正规资质？",
                    "questions": [
                        {
                            "question_text": "这家公司有哪些正规资质和证书编号？",
                            "keyword_layer": "proof",
                            "knowledge_need": "需要证书名称、证书编号、有效期和官方核验入口。",
                            "search_asset_type": "qualification",
                        }
                    ],
                }
            ]
        }
    )

    question = groups[0]["questions"][0]
    assert question["keyword_layer"] == "proof"
    assert question["knowledge_need"] == "需要证书名称、证书编号、有效期和官方核验入口。"
    assert question["search_asset_type"] == "qualification"


def test_template_question_groups_fill_keyword_layer_and_asset_fields():
    project = SimpleNamespace(
        name="北方智造科技有限公司",
        industry="manufacturing_b2b",
        region="天津",
        notes="提供工业检测设备、产线巡检系统和售后维保服务。",
    )

    groups = _build_template_groups(project, "北方智造", facts=[])
    questions = [question for group in groups for question in group["questions"]]

    assert questions
    assert all(question.get("keyword_layer") for question in questions)
    assert all(question.get("knowledge_need") for question in questions)
    assert all(question.get("search_asset_type") for question in questions)
    assert {"category", "proof", "conversion", "comparison"} & {
        question["keyword_layer"] for question in questions
    }
