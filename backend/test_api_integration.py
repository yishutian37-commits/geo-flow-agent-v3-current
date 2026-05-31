"""
GEO Flow Agent V2 API 集成测试脚本
系统性测试所有核心功能模块
"""
import httpx
import pytest
import sys
import uuid

BASE_URL = "http://localhost:8000/api/v1"


def _external_server_available():
    try:
        return httpx.get("http://localhost:8000/health", timeout=0.5).status_code < 500
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _external_server_available(),
    reason="External API server is not running on localhost:8000",
)

# 全局状态
state = {
    "project_id": None,
    "brand_id": None,
    "fact_id": None,
    "corpus_id": None,
    "question_group_id": None,
    "question_id": None,
    "task_id": None,
    "draft_id": None,
    "monitoring_run_id": None,
}

errors = []

def log(title, detail=""):
    print(f"\n{'='*60}")
    print(f"  {title}")
    if detail:
        print(f"  {detail}")
    print('='*60)

def report_error(step, msg, response=None):
    err = {"step": step, "message": msg}
    if response:
        err["status"] = response.status_code
        err["body"] = response.text[:500]
    errors.append(err)
    print(f"  [ERROR] [{step}]: {msg}")
    if response:
        print(f"      Status: {response.status_code}, Body: {response.text[:200]}")

def check(step, response, expected_status=200):
    if response.status_code != expected_status:
        report_error(step, f"Expected {expected_status}, got {response.status_code}", response)
        return False
    print(f"  [OK] {step}")
    return True


def test_health():
    log("1. Health Check")
    r = httpx.get("http://localhost:8000/health", timeout=10)
    return check("Health endpoint", r)


def test_projects():
    log("2. Projects API")

    # 2.1 Create project
    r = httpx.post(f"{BASE_URL}/projects", json={
        "name": "测试项目-无人机培训",
        "industry": "education_training",
        "region": "包头",
        "budget": 50000,
        "notes": "职业技能培训项目"
    })
    if not check("Create project", r, 200):
        return False
    data = r.json()
    state["project_id"] = data["id"]
    print(f"      Project ID: {state['project_id']}")

    # 2.2 List projects
    r = httpx.get(f"{BASE_URL}/projects")
    if not check("List projects", r):
        return False

    # 2.3 Get project detail
    r = httpx.get(f"{BASE_URL}/projects/{state['project_id']}")
    if not check("Get project detail", r):
        return False

    # 2.4 Get project brands (should be empty initially)
    r = httpx.get(f"{BASE_URL}/projects/{state['project_id']}/brands")
    if not check("Get project brands (empty)", r):
        return False
    brands = r.json()
    if brands:
        state["brand_id"] = brands[0]["id"]

    # 2.5 Diagnose gaps
    r = httpx.post(f"{BASE_URL}/projects/{state['project_id']}/diagnose-gaps", json=[
        "training_qualification", "instructor_profiles", "address", "phone"
    ])
    if not check("Diagnose gaps", r):
        return False
    gap_data = r.json()
    print(f"      Completeness: {gap_data.get('completeness_score')}%")
    if gap_data.get('missing_required'):
        print(f"      Missing required: {len(gap_data['missing_required'])}")

    return True


def test_brands():
    log("3. Brands API")
    if not state["project_id"]:
        report_error("Create brand", "No project_id")
        return False

    # Create brand under project
    r = httpx.post(f"{BASE_URL}/brands", json={
        "project_id": state["project_id"],
        "brand_name": "包头无人机学院",
        "company_name": "包头无人机科技有限公司",
        "official_site": "https://example.com",
        "description": "专业无人机培训机构"
    })
    if not check("Create brand", r, 200):
        # brands endpoint might be minimal, try to get from project
        r2 = httpx.get(f"{BASE_URL}/projects/{state['project_id']}/brands")
        if r2.status_code == 200 and r2.json():
            state["brand_id"] = r2.json()[0]["id"]
            print(f"      Brand ID from project: {state['brand_id']}")
            return True
        return False

    data = r.json()
    state["brand_id"] = data.get("id")
    print(f"      Brand ID: {state['brand_id']}")
    return True


def test_brand_facts():
    log("4. Brand Facts API")
    if not state["brand_id"]:
        report_error("Brand facts", "No brand_id")
        return False

    # 4.1 Create fact
    r = httpx.post(f"{BASE_URL}/brand-facts", json={
        "brand_id": state["brand_id"],
        "fact_type": "qualification",
        "value": "拥有CAAC民用无人机驾驶执照培训资质",
        "public_wording": "持有中国民航局认证的无人机驾驶培训资质",
        "fact_scope": "public",
        "source": "官方资质文件",
        "risk_level": "low"
    })
    if not check("Create brand fact", r, 200):
        return False
    state["fact_id"] = r.json()["id"]
    print(f"      Fact ID: {state['fact_id']}")

    # 4.2 List facts by project
    r = httpx.get(f"{BASE_URL}/brand-facts", params={"project_id": state["project_id"]})
    if not check("List facts by project", r):
        return False
    facts = r.json()
    print(f"      Facts count for project: {len(facts)}")

    # 4.3 Confirm fact
    r = httpx.post(f"{BASE_URL}/brand-facts/{state['fact_id']}/confirm", json={
        "confirmed_by": "00000000-0000-0000-0000-000000000000",
        "public_wording": "持有中国民航局认证的无人机驾驶培训资质"
    })
    if not check("Confirm fact", r, 200):
        return False
    if r.json().get("status") != "confirmed":
        report_error("Confirm fact", f"Status not confirmed: {r.json().get('status')}")
        return False

    # 4.4 Check facts for publish
    r = httpx.post(f"{BASE_URL}/brand-facts/check-for-publish", json=[state["fact_id"]])
    if not check("Check facts for publish", r):
        return False
    pub_check = r.json()
    print(f"      Can publish: {pub_check.get('can_publish')}")
    if not pub_check.get("can_publish"):
        report_error("Check publish", f"Should be publishable: {pub_check}")

    return True


def test_corpus_items():
    log("5. Corpus Items API")
    if not state["project_id"]:
        report_error("Corpus items", "No project_id")
        return False

    # 5.1 Create corpus item
    r = httpx.post(f"{BASE_URL}/corpus-items", params={
        "project_id": state["project_id"],
        "title": "机构介绍资料",
        "content": "包头无人机学院成立于2018年，拥有CAAC培训资质，位于青山区。联系电话：0472-1234567。培训课程包括多旋翼、固定翼无人机驾驶。",
        "source_type": "official_document",
        "contains_factual_claim": True
    })
    if not check("Create corpus item", r, 200):
        return False
    state["corpus_id"] = r.json()["id"]
    print(f"      Corpus ID: {state['corpus_id']}")

    # 5.2 List corpus items
    r = httpx.get(f"{BASE_URL}/corpus-items", params={"project_id": state["project_id"]})
    if not check("List corpus items", r):
        return False

    # 5.3 Extract fact from corpus
    r = httpx.post(f"{BASE_URL}/brand-facts/extract-from-corpus", json={
        "corpus_item_id": state["corpus_id"],
        "suggested_facts": [
            {
                "brand_id": state["brand_id"],
                "fact_type": "contact",
                "value": "0472-1234567",
                "public_wording": "咨询电话：0472-1234567",
                "fact_scope": "public"
            }
        ]
    })
    if not check("Extract fact from corpus", r, 200):
        return False
    extracted = r.json()
    print(f"      Extracted facts: {len(extracted)}")

    return True


def test_question_bank():
    log("6. Question Bank API")
    if not state["project_id"]:
        report_error("Question bank", "No project_id")
        return False

    # 6.1 Generate question bank
    r = httpx.post(f"{BASE_URL}/projects/{state['project_id']}/generate-question-bank", params={
        "brand_name": "包头无人机学院"
    })
    if not check("Generate question bank", r, 200):
        return False
    q_data = r.json()
    print(f"      Generated groups: {q_data.get('generated_groups')}")

    # 6.2 List question groups
    r = httpx.get(f"{BASE_URL}/questions/groups", params={"project_id": state["project_id"]})
    if not check("List question groups", r):
        return False
    groups = r.json()
    if not groups:
        report_error("Question groups", "No groups found after generation")
        return False
    state["question_group_id"] = groups[0]["id"]
    print(f"      Question groups: {len(groups)}")

    # 6.3 Add question to group
    r = httpx.post(f"{BASE_URL}/questions/groups/{state['question_group_id']}/questions", json={
        "question_text": "包头无人机学院的培训费用是多少？",
        "priority": 80,
        "sample_policy": "mvp"
    })
    if not check("Add question", r, 200):
        return False
    state["question_id"] = r.json()["id"]

    return True


def test_content_tasks():
    log("7. Content Tasks API")
    if not state["project_id"]:
        report_error("Content tasks", "No project_id")
        return False

    # 7.1 Create task
    r = httpx.post(f"{BASE_URL}/content-tasks", json={
        "project_id": state["project_id"],
        "content_type": "brand_intro",
        "layer": "verification_layer",
        "priority": "high",
        "status": "draft"
    })
    if not check("Create content task", r, 200):
        return False
    state["task_id"] = r.json()["id"]
    print(f"      Task ID: {state['task_id']}")

    # 7.2 List tasks
    r = httpx.get(f"{BASE_URL}/content-tasks", params={"project_id": state["project_id"]})
    if not check("List content tasks", r):
        return False

    return True


def test_content_drafts():
    log("8. Content Drafts API")
    if not state["task_id"]:
        report_error("Content drafts", "No task_id")
        return False

    # 8.1 Generate draft (requires LLM, might fail without API key)
    r = httpx.post(f"{BASE_URL}/content-drafts/{state['task_id']}/generate", json={
        "content_type": "brand_intro",
        "platform": "media"
    })
    # We accept both 200 (success) and 500 (LLM error) to record the behavior
    if r.status_code == 200:
        check("Generate draft (LLM)", r)
        state["draft_id"] = r.json().get("draft", {}).get("id")
        print(f"      Draft ID: {state['draft_id']}")
    else:
        print(f"  ⚠️ Generate draft returned {r.status_code} (expected if no LLM key configured)")
        print(f"      Body: {r.text[:200]}")

    # 8.2 Create manual draft
    r = httpx.post(f"{BASE_URL}/content-drafts", json={
        "task_id": state["task_id"],
        "title": "包头无人机学院品牌介绍",
        "body": "包头无人机学院成立于2018年，是本地专业的无人机培训机构。",
        "status": "draft",
        "risk_level": "low"
    })
    if not check("Create manual draft", r, 200):
        return False
    if not state["draft_id"]:
        state["draft_id"] = r.json()["id"]

    # 8.3 List drafts
    r = httpx.get(f"{BASE_URL}/content-drafts", params={"task_id": state["task_id"]})
    if not check("List drafts", r):
        return False

    # 8.4 Validate publish ready
    if state["draft_id"]:
        r = httpx.post(f"{BASE_URL}/content-drafts/{state['draft_id']}/validate-publish-ready")
        if not check("Validate publish ready", r):
            return False
        val = r.json()
        print(f"      Can publish: {val.get('can_publish')}, Issues: {val.get('total_issues')}")

    return True


def test_monitoring():
    log("9. Monitoring API")
    if not state["project_id"] or not state["question_id"]:
        report_error("Monitoring", "Missing project_id or question_id")
        return False

    # Need a model_target_id - create one via projects or use a fake one
    model_target_id = str(uuid.uuid4())

    # 9.1 Create monitoring run
    r = httpx.post(f"{BASE_URL}/monitoring/runs", params={
        "project_id": state["project_id"],
        "run_type": "routine",
        "mechanism_type": "B",
        "model_target_id": model_target_id,
        "sample_policy": "mvp"
    })
    if not check("Create monitoring run", r, 200):
        return False
    state["monitoring_run_id"] = r.json()["id"]
    print(f"      Monitoring Run ID: {state['monitoring_run_id']}")

    # 9.2 Add sample
    r = httpx.post(f"{BASE_URL}/monitoring/runs/{state['monitoring_run_id']}/samples", params={
        "question_id": state["question_id"],
        "answer_text": "包头无人机学院是一家专业的培训机构，拥有CAAC资质。",
        "brand_mentioned": True,
        "recommended": True,
        "position": 2,
        "list_length": 5,
        "explicit_citations": 1,
        "inferred_source_matches": 0
    })
    if not check("Add monitoring sample", r, 200):
        return False

    # 9.3 Calculate metrics
    r = httpx.post(f"{BASE_URL}/monitoring/runs/{state['monitoring_run_id']}/calculate")
    if not check("Calculate metrics", r, 200):
        return False
    metrics = r.json()
    print(f"      Sample count: {metrics.get('sample_count')}")
    print(f"      Confidence level: {metrics.get('confidence_level')}")
    if metrics.get("metrics"):
        print(f"      Mention rate: {metrics['metrics'].get('brand_mention_rate', {}).get('point_estimate')}%")

    return True


def test_dashboard():
    log("10. Dashboard Stats API")
    r = httpx.get(f"{BASE_URL}/dashboard/stats")
    if not check("Dashboard stats", r):
        return False
    stats = r.json()
    print(f"      Projects: {stats.get('projects', {})}")
    print(f"      Facts: {stats.get('facts', {})}")
    print(f"      Tasks: {stats.get('tasks', {})}")
    print(f"      Monitoring: {stats.get('monitoring', {})}")
    print(f"      Todos: {len(stats.get('todos', []))}")
    return True


def test_ai_models():
    log("11. AI Models API")
    r = httpx.get(f"{BASE_URL}/ai-models/providers")
    if not check("List AI providers", r):
        return False
    r = httpx.get(f"{BASE_URL}/ai-models/registry")
    if not check("List registry", r):
        return False
    return True


def run_all_tests():
    print("\n" + "="*60)
    print("  GEO Flow Agent V2 - API Integration Test Suite")
    print("="*60)

    tests = [
        test_health,
        test_projects,
        test_brands,
        test_brand_facts,
        test_corpus_items,
        test_question_bank,
        test_content_tasks,
        test_content_drafts,
        test_monitoring,
        test_dashboard,
        test_ai_models,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            report_error(test.__name__, f"Exception: {str(e)}")

    print("\n" + "="*60)
    print(f"  Test Results: {passed} passed, {failed} failed")
    print(f"  Total errors recorded: {len(errors)}")
    print("="*60)

    if errors:
        print("\n  Detailed Errors:")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. [{err['step']}] {err['message']}")
            if 'status' in err:
                print(f"      HTTP {err['status']}: {err.get('body', '')}")

    print(f"\n  Final state: {state}")
    return errors


if __name__ == "__main__":
    errs = run_all_tests()
    sys.exit(1 if errs else 0)
