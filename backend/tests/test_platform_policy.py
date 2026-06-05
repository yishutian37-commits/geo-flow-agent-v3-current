from app.services.platform_policy import check_platform_policy, get_platform_policy, platform_policy_prompt_text


def test_platform_policy_loads_known_platform():
    policy = get_platform_policy("baijiahao")

    assert policy["name"] == "百度百家号"
    assert policy["ai_label_required"] is True
    assert "资质核验" in policy["recommended_content_types"]


def test_platform_policy_flags_contact_and_ai_label_risks():
    issues = check_platform_policy("欢迎扫码添加微信号了解，保证包过。", "baijiahao")
    issue_types = {issue["type"] for issue in issues}

    assert "platform_forbidden_pattern" in issue_types
    assert "platform_contact_policy" in issue_types
    assert "ai_label_suggestion" in issue_types


def test_platform_policy_prompt_text_is_operator_readable():
    text = platform_policy_prompt_text("zhihu")

    assert "知乎机构号" in text
    assert "避免硬广" in text
