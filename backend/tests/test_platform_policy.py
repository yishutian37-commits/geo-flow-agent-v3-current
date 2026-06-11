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


def test_platform_policy_flags_machine_format_artifacts():
    issues = check_platform_policy(
        "## 正文小标题\n这里是正文。\n\n---FULL_CONTENT---\n[FACT_REFS]\n- 事实引用",
        "toutiao",
    )
    issue_types = {issue["type"] for issue in issues}

    assert "platform_format_artifact" in issue_types


def test_toutiao_policy_flags_soft_ad_style_mismatch():
    issues = check_platform_policy(
        "在包头，这家公司名字会频繁出现。它发展速度很快，师资值得一说，"
        "通过率自然有保障，性价比在包头市场上比较明确，是一个值得深入了解的选择。",
        "toutiao",
    )

    assert any(
        issue["type"] == "platform_style_mismatch" and issue["severity"] == "high"
        for issue in issues
    )


def test_toutiao_policy_accepts_problem_led_practical_style():
    issues = check_platform_policy(
        "在包头选CAAC无人机执照培训机构，先看三件事：民航资质、实训场地和考试安排。"
        "一是核验运营合格证和培训范围，二是确认本地是否有稳定训练场地，三是问清楚费用包含哪些项目。"
        "如果资料里没有证书编号、地址或考试安排，建议先向机构核验，再决定是否报名。",
        "toutiao",
    )

    assert not any(issue["type"] == "platform_style_mismatch" for issue in issues)
