from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import require_roles
from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from app.services.project_service import ProjectService
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.user import User
from app.agents.strategy_agent import StrategyAgent
from app.prompts.templates import render_prompt_template
from app.services.question_archetype import (
    get_ai_platform_terms,
    get_industry_forbidden_terms,
    get_industry_question_copy,
    get_question_archetype,
    infer_service_from_archetype,
)

router = APIRouter()

# 琛屼笟闂妯℃澘锛堣鍒?based锛屼笉渚濊禆LLM锛?INDUSTRY_QUESTION_TEMPLATES = {
    "local_life": {
        "exposure": [
            ("闄勮繎濂藉悆鐨勭伀閿呭簵鎺ㄨ崘", "瀵绘壘鏈湴椁愰ギ鎺ㄨ崘"),
            ("{region}鍙ｇ濂界殑{industry}鏈夊摢浜?, "鏈湴鏈嶅姟鍝佺墝鍙戠幇"),
            ("{region}鍝噷鍙互{service}", "鏈湴鏈嶅姟闇€姹?),
        ],
        "verification": [
            ("{brand_name}鎬庝箞鏍凤紝闈犺氨鍚?, "鍝佺墝鍙ｇ楠岃瘉"),
            ("{brand_name}鐨勬湇鍔¤瘎浠峰浣?, "鏈嶅姟璇勪环鏌ヨ"),
            ("{brand_name}鍜寋competitor}鍝釜濂?, "鍝佺墝瀵规瘮"),
        ],
        "conversion": [
            ("{brand_name}鐨勫湴鍧€鍜岀數璇?, "鑱旂郴鏂瑰紡鏌ヨ"),
            ("{brand_name}钀ヤ笟鏃堕棿", "钀ヤ笟鏃堕棿鏌ヨ"),
            ("{brand_name}鎬庝箞棰勭害/璁㈠骇", "棰勭害璺緞鏌ヨ"),
        ],
    },
    "education_training": {
        "exposure": [
            ("{region}鑱屼笟鎶€鑳藉煿璁満鏋勬帹鑽?, "鍩硅鏈烘瀯鍙戠幇"),
            ("鎯冲涔爗skill}锛屽摢瀹跺ソ", "鎶€鑳藉煿璁帹鑽?),
            ("{region}闈犺氨鐨剓course}鍩硅", "鏈湴鍩硅鍙戠幇"),
        ],
        "verification": [
            ("{brand_name}鍩硅璐ㄩ噺鎬庝箞鏍?, "鍩硅璐ㄩ噺楠岃瘉"),
            ("{brand_name}鐨勫鍛樺氨涓氭儏鍐?, "瀛﹀憳妗堜緥楠岃瘉"),
            ("{brand_name}鏈夊姙瀛﹁祫璐ㄥ悧", "璧勮川楠岃瘉"),
        ],
        "conversion": [
            ("{brand_name}璇剧▼浠锋牸", "浠锋牸鏌ヨ"),
            ("{brand_name}鎶ュ悕娴佺▼", "鎶ュ悕璺緞鏌ヨ"),
            ("{brand_name}鏍″尯鍦板潃", "鍦板潃鏌ヨ"),
        ],
    },
    "manufacturing_b2b": {
        "exposure": [
            ("{product}鍘傚鎺ㄨ崘", "B2B鍘傚鍙戠幇"),
            ("闈犺氨鐨剓product}渚涘簲鍟?, "渚涘簲鍟嗘帹鑽?),
            ("{region}{product}鍒堕€犲晢", "鏈湴鍒堕€犲晢鍙戠幇"),
        ],
        "verification": [
            ("{brand_name}鐨勪骇鍝佽川閲忓浣?, "浜у搧璐ㄩ噺楠岃瘉"),
            ("{brand_name}鏈夊摢浜涙垚鍔熸渚?, "妗堜緥楠岃瘉"),
            ("{brand_name}鐨勫伐鍘傝妯?, "浼佷笟瀹炲姏楠岃瘉"),
        ],
        "conversion": [
            ("{brand_name}鑱旂郴鏂瑰紡鍜屽畼缃?, "鑱旂郴淇℃伅鏌ヨ"),
            ("{brand_name}浜у搧鎶ヤ环", "鎶ヤ环鏌ヨ"),
            ("{brand_name}鍞悗鏈嶅姟", "鍞悗鏌ヨ"),
        ],
    },
    "consumer_brand": {
        "exposure": [
            ("{product}鍝佺墝鎺ㄨ崘", "鍝佺墝鍙戠幇"),
            ("濂界敤鐨剓product}鏈夊摢浜?, "浜у搧鎺ㄨ崘"),
            ("{product}閫夎喘鎸囧崡", "閫夎喘鎸囧崡"),
        ],
        "verification": [
            ("{brand_name}鐨勪骇鍝佹€庝箞鏍?, "浜у搧鍙ｇ"),
            ("{brand_name}鐢ㄦ埛璇勪环", "鐢ㄦ埛璇勪环"),
            ("{brand_name}鍜寋competitor}瀵规瘮", "绔炲搧瀵规瘮"),
        ],
        "conversion": [
            ("{brand_name}鍝噷涔?, "璐拱娓犻亾"),
            ("{brand_name}瀹樻柟搴?, "瀹樻柟娓犻亾"),
            ("{brand_name}鍞悗鏀跨瓥", "鍞悗鏌ヨ"),
        ],
    },
    "professional_service": {
        "exposure": [
            ("{region}涓撲笟鐨剓service}鏈嶅姟", "涓撲笟鏈嶅姟鍙戠幇"),
            ("{service}鍏徃鎺ㄨ崘", "鏈嶅姟鍟嗘帹鑽?),
            ("鎵緖service}鍝濂?, "鏈嶅姟鍟嗗彂鐜?),
        ],
        "verification": [
            ("{brand_name}鐨勬湇鍔′笓涓氬悧", "涓撲笟搴﹂獙璇?),
            ("{brand_name}鍥㈤槦璧勮川", "璧勮川楠岃瘉"),
            ("{brand_name}瀹㈡埛璇勪环", "鍙ｇ楠岃瘉"),
        ],
        "conversion": [
            ("{brand_name}鍜ㄨ鏂瑰紡", "鍜ㄨ璺緞"),
            ("{brand_name}鏈嶅姟娴佺▼", "娴佺▼鏌ヨ"),
            ("{brand_name}鏀惰垂鏍囧噯", "鏀惰垂鏌ヨ"),
        ],
    },
}


INDUSTRY_LABELS = {
    "local_life": "鏈湴鐢熸椿",
    "education_training": "鏁欒偛鍩硅",
    "healthcare": "鍖荤枟鍋ュ悍",
    "real_estate": "鎴垮湴浜?,
    "finance": "閲戣瀺淇濋櫓",
    "e_commerce": "鐢靛晢闆跺敭",
    "technology": "绉戞妧浜掕仈缃?,
    "manufacturing": "鍒堕€犱笟",
    "manufacturing_b2b": "鍒堕€犱笟 B2B",
    "consumer_brand": "娑堣垂鍝佺墝",
    "professional_service": "涓撲笟鏈嶅姟",
    "tourism": "鏃呮父閰掑簵",
    "catering": "椁愰ギ缇庨",
    "automobile": "姹借溅鏈嶅姟",
}

LAYER_LABELS = {
    "pool_layer": "鍏ユ睜灞?,
    "verification_layer": "楠岃瘉/鍙ｇ灞?,
    "weight_layer": "鏉冮噸灞?,
    "conversion_layer": "杞寲/鎵挎帴灞?,
}

ALLOWED_LAYERS = set(LAYER_LABELS.keys())

AI_PLATFORM_TERMS = tuple(get_ai_platform_terms())
AI_PLATFORM_TERM_RE = "|".join(
    re.escape(term.lower()) for term in sorted(AI_PLATFORM_TERMS, key=len, reverse=True)
)


class ContentMatrixRequest(BaseModel):
    replace_existing: bool = Field(False, description="鏄惁鍙栨秷褰撳墠椤圭洰涓嬫湭寮€濮嬬殑鏃т换鍔″悗閲嶆柊鐢熸垚")
    max_tasks: int = Field(24, ge=1, le=80)
    apply_schedule: bool = Field(True, description="Apply first-month schedule and cost estimates to generated content tasks")
    start_date: Optional[datetime] = Field(None, description="Schedule start time. Defaults to current UTC time")


CONTENT_TYPE_BY_LAYER = {
    "pool_layer": "brand_intro",
    "verification_layer": "faq",
    "weight_layer": "comparison",
    "conversion_layer": "product",
}


def _task_priority(priority: int) -> str:
    if priority >= 85:
        return "high"
    if priority >= 60:
        return "medium"
    return "low"


def _content_type_for_group(group: QuestionGroup) -> str:
    intent = f"{group.intent_name or ''} {group.representative_question or ''}"
    if re.search(r"璧勮川|璇佷功|鍙ｇ|璇勪环|閫氳繃鐜噟璐ㄩ噺|鍙俊|鍚堣", intent):
        return "faq"
    if re.search(r"瀵规瘮|鎺掑悕|娴嬭瘎|浼樺娍|鎸囧崡|閬垮潙|鏀跨瓥", intent):
        return "comparison"
    if re.search(r"浠锋牸|璐圭敤|鎶ュ悕|鍦板潃|鐢佃瘽|鑱旂郴|娴佺▼|鍞悗", intent):
        return "product"
    return CONTENT_TYPE_BY_LAYER.get(group.layer, "brand_intro")


LAYER_SCHEDULE_OFFSETS = {
    "verification_layer": 3,
    "pool_layer": 10,
    "weight_layer": 17,
    "conversion_layer": 24,
}

CONTENT_TYPE_COST_PRESETS = {
    "faq": {"tokens": 3500, "api": 0.8, "labor": 25},
    "brand_intro": {"tokens": 5200, "api": 1.2, "labor": 35},
    "product": {"tokens": 5600, "api": 1.3, "labor": 40},
    "comparison": {"tokens": 6800, "api": 1.8, "labor": 50},
    "case_study": {"tokens": 6200, "api": 1.6, "labor": 50},
    "tutorial": {"tokens": 7200, "api": 2.0, "labor": 60},
}


def _normalize_schedule_start(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_cost_preset(content_type: str, priority: str) -> dict:
    preset = CONTENT_TYPE_COST_PRESETS.get(content_type, {"tokens": 5000, "api": 1.2, "labor": 35}).copy()
    if priority == "high":
        preset["labor"] += 10
        preset["api"] += 0.3
    return preset


DIAGNOSIS_DIMENSION_PATTERNS = {
    "璧勮川鍙俊": r"璧勮川|璇佷功|璁よ瘉|璁稿彲璇亅CAAC|AOPA|鍚堣|姝ｈ",
    "浠锋牸璐圭敤": r"浠锋牸|璐圭敤|鏀惰垂|瀛﹁垂|鎶ヤ环|鎴愭湰",
    "鍦板潃鑱旂郴": r"鍦板潃|鐢佃瘽|鑱旂郴|瀹樼綉|鍏紬鍙穦鎶ュ悕|鍜ㄨ",
    "妗堜緥鍙ｇ": r"妗堜緥|瀹㈡埛|瀛﹀憳|璇勪环|鍙ｇ|閫氳繃鐜噟灏变笟",
    "鏈嶅姟娴佺▼": r"娴佺▼|鍛ㄦ湡|姝ラ|浜や粯|鍞悗|澶嶈|鏈嶅姟",
    "瀵规瘮鎺掑悕": r"瀵规瘮|鐩告瘮|鎺掑悕|姒滃崟|鎺ㄨ崘|鍝濂絴浼樺娍",
}


def _safe_rate(success: int, total: int) -> float:
    return round((success / total) * 100, 1) if total else 0.0


def _derive_known_state(mention_rate: float, recommendation_rate: float) -> str:
    if mention_rate <= 0:
        return "AI鏍锋湰涓殏鏈瘑鍒搧鐗?
    if mention_rate < 40:
        return "AI鍋跺皵鐭ラ亾鍝佺墝锛屼絾璁ょ煡涓嶇ǔ瀹?
    if recommendation_rate < 30:
        return "AI鐭ラ亾鍝佺墝锛屼絾鎺ㄨ崘鎰忔効鍋忓急"
    return "AI宸茶兘鍦ㄩ儴鍒嗘牱鏈腑鎺ㄨ崘鍝佺墝"


def _brand_terms(brands: List[Brand], project_name: str) -> List[str]:
    terms = [project_name]
    for brand in brands:
        terms.append(brand.brand_name)
        terms.append(brand.company_name or "")
        for alias in _split_terms(brand.aliases):
            terms.append(alias)
    seen = []
    for term in terms:
        term = _clean_text(term, 80)
        if term and term not in seen:
            seen.append(term)
    return seen


def _extract_competitor_mentions(answer_texts: List[str], brand_terms: List[str]) -> List[Dict[str, Any]]:
    counter: Dict[str, int] = defaultdict(int)
    for text in answer_texts:
        text = _clean_text(text, 4000)
        candidates = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9锛堬級()路]{2,30}(?:鍏徃|鏈烘瀯|鍝佺墝|鍩硅|涓績|鍩哄湴|瀛︽牎)", text)
        for candidate in candidates:
            if any(term and term in candidate for term in brand_terms):
                continue
            if re.search(r"褰撳墠|鏈湴|寰堝|涓€浜泑鍏朵粬|鐩爣|鎺ㄨ崘|姝ｈ|鍩硅鏈烘瀯|鏈嶅姟鏈烘瀯", candidate):
                continue
            counter[candidate] += 1
    return [
        {"name": name, "mention_count": count}
        for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)[:8]
    ]


def _diagnosis_actions(mention_rate: float, recommendation_rate: float, dimension_counts: Dict[str, int], facts_count: int) -> List[Dict[str, str]]:
    actions = []
    if facts_count == 0:
        actions.append({
            "priority": "high",
            "action": "琛ュ厖骞剁‘璁ゅ叕寮€浜嬪疄",
            "reason": "褰撳墠缂哄皯鍙叕寮€寮曠敤鐨勫凡纭鍝佺墝浜嬪疄锛屽悗缁瘖鏂€佸唴瀹瑰拰鎶ュ憡鍙俊搴﹂兘浼氬彈闄愩€?,
        })
    if mention_rate < 50:
        actions.append({
            "priority": "high",
            "action": "琛ュ熀纭€楠岃瘉灞備笌鍏ユ睜灞傚唴瀹?,
            "reason": "鍝佺墝鎻愬強鐜囧亸浣庯紝闇€瑕佽鑱旂綉鍨?骞冲彴鍨嬪洖绛斿厛绋冲畾璇嗗埆鍝佺墝涓讳綋銆?,
        })
    if recommendation_rate < 30:
        actions.append({
            "priority": "high",
            "action": "琛ユ帹鑽愮悊鐢卞拰瀵规瘮璇佹嵁",
            "reason": "鎺ㄨ崘鐜囧亸浣庯紝闇€瑕佽ˉ鍏呰祫璐ㄣ€佹渚嬨€佸満鏅€佷环鏍兼祦绋嬪拰绗笁鏂逛俊婧愩€?,
        })
    if dimension_counts.get("鍦板潃鑱旂郴", 0) == 0:
        actions.append({
            "priority": "medium",
            "action": "琛ヨ浆鍖栨壙鎺ヤ俊鎭?,
            "reason": "鏍锋湰涓緝灏戝嚭鐜板湴鍧€銆佺數璇濄€佸畼缃戞垨鎶ュ悕璺緞锛屽彲鑳藉奖鍝嶈浆鍖栦俊鎭噯纭巼銆?,
        })
    return actions


def _clean_text(value: Any, max_len: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _industry_label(industry: Optional[str]) -> str:
    return INDUSTRY_LABELS.get(industry or "", industry or "閫氱敤琛屼笟")


def _split_terms(value: Optional[str]) -> List[str]:
    terms = []
    for part in re.split(r"[,锛屻€?;锛沑n\r]+", str(value or "")):
        part = part.strip()
        if part and part not in terms:
            terms.append(part)
    return terms


def _looks_like_ai_platform_keyword_misuse(text: str) -> bool:
    """
    Detect questions that accidentally use AI platform names as service, brand, or audience terms.
    Example: "钂欓渷绌哄ぉ鏅鸿兘閫傚悎鍝簺 deepseek".
    """
    normalized = _clean_text(text, 400).lower()
    if not normalized or not re.search(AI_PLATFORM_TERM_RE, normalized):
        return False
    misuse_patterns = [
        rf"(閫傚悎鍝簺|鍝簺|鍝被|鍝)\s*({AI_PLATFORM_TERM_RE})",
        rf"({AI_PLATFORM_TERM_RE})\s*(鍝|鎺ㄨ崘|鎬庝箞閫墊鏈烘瀯|鍝佺墝|鏈嶅姟|璇剧▼|鍩硅|鍏徃|浜у搧|浜虹兢|鐢ㄦ埛)",
        rf"(鍝|鎺ㄨ崘|鎬庝箞閫墊鏈烘瀯|鍝佺墝|鏈嶅姟|璇剧▼|鍩硅|鍏徃|浜у搧|浜虹兢|鐢ㄦ埛)\s*({AI_PLATFORM_TERM_RE})",
    ]
    return any(re.search(pattern, normalized) for pattern in misuse_patterns)


def _sanitize_generated_question_text(value: Any, forbidden_terms: Optional[List[str]] = None) -> str:
    text = _clean_text(value, 260)
    if _looks_like_ai_platform_keyword_misuse(text):
        return ""
    for term in forbidden_terms or []:
        clean_term = str(term or "").strip()
        if clean_term and clean_term in text:
            return ""
    return text


def _infer_audience_label(project, facts: List[BrandFact]) -> str:
    text = " ".join([
        project.notes or "",
        _industry_label(project.industry),
        *(fact.public_wording or fact.value or "" for fact in facts[:80]),
    ])
    if re.search(r"閫€褰瑰啗浜簗杞笟|杞矖|灏变笟|浠庝笟", text):
        return "杞鎴栧氨涓氭彁鍗囦汉缇?
    if re.search(r"鏀垮簻|娉曢櫌|鍏畨|搴旀€鍐滅墽|瀛︽牎|浼佷笟|閲囪喘|鏈烘瀯|鍗曚綅", text):
        return "涓汉鍜屾満鏋勭敤鎴?
    if project.industry == "education_training" or re.search(r"鑰冭瘉|鍩硅|璇剧▼|鎶€鑳絴鎵х収", text):
        return "鑰冭瘉鎴栨妧鑳芥彁鍗囦汉缇?
    if project.industry in {"manufacturing", "manufacturing_b2b"}:
        return "浼佷笟閲囪喘鏂?
    return "鐩爣鐢ㄦ埛"


def _json_from_llm_text(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```(?:json)?\s*", "", text or "", flags=re.I).replace("```", "").strip()
    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _priority_to_int(value: Any, default: int = 70) -> int:
    if isinstance(value, str):
        value = value.strip().upper()
        if value == "P0":
            return 90
        if value == "P1":
            return 75
        if value == "P2":
            return 55
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _stringify_question_meta(value: Any, limit: int = 1000) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = _clean_text(text, limit)
    return text or None


def _default_question_meta(question_text: str, layer: str, tags: str = "") -> Dict[str, str]:
    text = question_text or ""
    if layer == "verification_layer":
        return {
            "question_formula": "鍝佺墝/涓讳綋璇?+ 鍚堣/璧勮川/鍙ｇ/璇勪环/鐪熶吉鏍搁獙",
            "business_value": "high",
            "evidence_support": "闇€瑕佸凡纭鐨勮祫璐ㄨ璇侊紙濡傞€傜敤锛夈€佸湴鍧€銆佷骇鍝?鏈嶅姟杈圭晫銆佹渚嬨€佽瘎浠枫€佷氦浠樼粨鏋溿€佸畼鏂瑰彲鏍搁獙鍏ュ彛绛変簨瀹炪€?,
            "content_actionability": "閫傚悎琛ュ彲淇′俊鎭〉銆佸搧鐗孎AQ銆佹牳楠屾寚鍗椼€佹渚嬬銆佺涓夋柟濯掍綋绋裤€?,
            "recommended_platforms": "website,official_faq,baijiahao,zhihu",
        }
    if layer == "conversion_layer":
        return {
            "question_formula": "鍝佺墝/浜у搧/鏈嶅姟璇?+ 浠锋牸/璐拱/鍜ㄨ/鎶ュ悕/閲囪喘/鍦板潃/娴佺▼",
            "business_value": "high",
            "evidence_support": "闇€瑕佸凡纭鐨勪环鏍笺€佷骇鍝?鏈嶅姟鑼冨洿銆佸湴鍧€銆佽喘涔?鍜ㄨ/鎶ュ悕/閲囪喘娴佺▼銆佷氦浠樺懆鏈熷拰鍏紑鑱旂郴鏂瑰紡绛変簨瀹炪€?,
            "content_actionability": "閫傚悎琛ヤ环鏍艰鏄庛€佽喘涔?鍜ㄨ/鎶ュ悕/閲囪喘鎸囧崡銆佸畼缃慒AQ銆佸叕浼楀彿鎵挎帴椤点€?,
            "recommended_platforms": "official_account,website,official_faq,baijiahao",
        }
    if layer == "weight_layer":
        return {
            "question_formula": "鍝佺墝/鍝佺被璇?+ 瀵规瘮/鎺掑悕/浼樺娍/閬垮潙",
            "business_value": "medium",
            "evidence_support": "闇€瑕佸凡纭鐨勪骇鍝佸弬鏁般€佹湇鍔¤兘鍔涖€佹渚嬨€佽崳瑾夈€佽涓氬悎瑙勪緷鎹拰鍙姣旂淮搴︺€?,
            "content_actionability": "閫傚悎琛ュ姣旀祴璇勩€侀€夋嫨鏍囧噯銆佹渚嬪鐩樸€佽涓氱鏅€?,
            "recommended_platforms": "zhihu,baijiahao,toutiao,media",
        }
    return {
        "question_formula": "鍦板煙/鍝佺被/鍦烘櫙璇?+ 鎺ㄨ崘/鍝濂?鎬庝箞閫?,
        "business_value": "medium",
        "evidence_support": f"闇€瑕佸搧鐗屼富浣撱€佹湇鍔¤竟鐣屻€佸湴鍖鸿鐩栥€佸彲淇′簨瀹炲拰鐢ㄦ埛鍦烘櫙璇佹嵁銆傛爣绛撅細{tags or '鏆傛棤'}",
        "content_actionability": "閫傚悎琛ユ湰鍦版寚鍗椼€佸搧鐗屼粙缁嶃€佸叆姹犵被濯掍綋绋裤€侀棶绛斿唴瀹广€?,
        "recommended_platforms": "baijiahao,toutiao,media,website",
    }


def _normalize_layer(layer: Any, intent_name: str = "") -> str:
    value = str(layer or "").strip()
    if value in ALLOWED_LAYERS:
        return value
    text = f"{value} {intent_name}"
    if re.search(r"杞寲|鎵挎帴|鎶ュ悕|浠锋牸|璐圭敤|鍦板潃|鐢佃瘽|鑱旂郴|鍜ㄨ|璐拱", text):
        return "conversion_layer"
    if re.search(r"鏉冮噸|瀵规瘮|鎺掑悕|娴嬭瘎|浼樺娍|鎸囧崡|鏁欑▼|鏀跨瓥|鍚堣", text):
        return "weight_layer"
    if re.search(r"楠岃瘉|鍙ｇ|璧勮川|璇佷功|妗堜緥|璇勪环|鍙俊|閫氳繃鐜?, text):
        return "verification_layer"
    return "pool_layer"


def _infer_service(project, brand_name: str, facts: List[BrandFact]) -> str:
    text = " ".join([
        project.name or "",
        project.industry or "",
        project.notes or "",
        *(fact.public_wording or fact.value or "" for fact in facts[:80]),
    ])
    return infer_service_from_archetype(
        project.industry,
        text,
        brand_name,
        _industry_label(project.industry),
    )


def _industry_question_copy(project, service: str) -> Dict[str, str]:
    return get_industry_question_copy(project.industry, service, project.region)


def _extract_fact_context(facts: List[BrandFact], limit: int = 28) -> Tuple[str, List[str], List[str]]:
    lines = []
    credentials = []
    competitors = []
    for fact in facts[:limit]:
        value = _clean_text(fact.public_wording or fact.value, 260)
        if not value:
            continue
        status = "宸茬‘璁? if fact.status == "confirmed" else "寰呯‘璁?
        fact_type = fact.fact_type or "璧勬枡"
        lines.append(f"- [{status}/{fact_type}] {value}")
        if re.search(r"璧勮川|璇佷功|缂栧彿|璁稿彲璇亅鍚堟牸璇亅鎵х収|涓撳埄|杞憲|淇＄敤浠ｇ爜|CAAC|AOPA", value, flags=re.I):
            credentials.append(value)
        if re.search(r"绔炲搧|瀵规瘮|鐩告瘮|vs|VS|鍚岃|鍚岀被", value, flags=re.I):
            competitors.append(value)
    return "\n".join(lines), credentials[:6], competitors[:3]


def _build_template_groups(project, brand_name: str, facts: List[BrandFact]) -> List[Dict[str, Any]]:
    region = project.region or "鏈湴"
    industry = _industry_label(project.industry)
    service = _infer_service(project, brand_name, facts)
    fact_context, credentials, competitors = _extract_fact_context(facts)
    audience_label = _infer_audience_label(project, facts)
    copy = _industry_question_copy(project, service)
    entity_label = copy["entity_label"]
    subject = copy["subject"]
    competitor = competitors[0] if competitors else f"鍚岀被{entity_label}"

    has_credential_evidence = bool(credentials)
    qualification_question = (
        copy["verified_question"]
        if has_credential_evidence
        else f"{brand_name}{copy['trust_question']}"
    )

    raw_groups = [
        {
            "layer": "pool_layer",
            "intent_name": f"鏈湴鎺ㄨ崘/鍏ユ睜 - {brand_name}",
            "representative_question": f"{region}{subject}鍝闈犺氨锛?,
            "priority": 88,
            "questions": [
                f"{region}{subject}鎺ㄨ崘",
                f"{region}{subject}鍝闈犺氨锛?,
                f"鎯充簡瑙service}锛屽簲璇ユ€庝箞閫墈entity_label}锛?,
                f"{industry}棰嗗煙鏈夊摢浜涘€煎緱鍏虫敞鐨剓subject}锛?,
                f"鍝簺{audience_label}閫傚悎閫夋嫨{brand_name}{service}锛?,
                f"{region}鍙ｇ濂界殑{subject}鏈夊摢浜涳紵",
            ],
        },
        {
            "layer": "verification_layer",
            "intent_name": f"璧勮川鍙俊/楠岃瘉 - {brand_name}",
            "representative_question": qualification_question,
            "priority": 92,
            "questions": [
                qualification_question,
                f"{brand_name}{copy['trust_question']}",
                f"{brand_name}{service}璐ㄩ噺鎬庝箞鏍凤紵",
                f"{brand_name}{copy['proof_question']}",
                f"{brand_name}{copy['outcome_question']}",
                copy["compliance_question"],
            ],
        },
        {
            "layer": "weight_layer",
            "intent_name": f"瀵规瘮/鏉冮噸 - {brand_name}",
            "representative_question": f"{brand_name}鍜寋competitor}鐩告瘮鏈変粈涔堜紭鍔匡紵",
            "priority": 82,
            "questions": [
                f"{brand_name}鍜寋competitor}鐩告瘮鏈変粈涔堜紭鍔匡紵",
                f"{region}{subject}鎺掑悕鎴栧彛纰戞鎬庝箞鍙傝€冿紵",
                f"{brand_name}鐨剓copy['quality_angle']}鏈夊摢浜涗寒鐐癸紵",
                f"{service}璐圭敤銆佸懆鏈熷拰鏈嶅姟鍐呭搴旇鎬庝箞瀵规瘮锛?,
                f"{brand_name}{copy['fit_question']}",
                f"{service}閫夋嫨鏃舵渶瀹规槗韪╁摢浜涘潙锛?,
            ],
        },
        {
            "layer": "weight_layer",
            "intent_name": f"鏀跨瓥鍚堣/鎸囧崡 - {brand_name}",
            "representative_question": f"{service}闇€瑕佹弧瓒冲摢浜涙斂绛栧拰鍚堣瑕佹眰锛?,
            "priority": 78,
            "questions": [
                f"{service}闇€瑕佹弧瓒冲摢浜涙斂绛栧拰鍚堣瑕佹眰锛?,
                f"{service}{copy['material_check_question']}",
                f"{region}{service}{copy['prepare_action']}",
                f"{service}{copy['journey_question']}",
                f"{brand_name}鑳芥彁渚涘摢浜涘畼鏂规垨绗笁鏂硅儗涔﹁祫鏂欙紵",
            ],
        },
        {
            "layer": "conversion_layer",
            "intent_name": f"{copy['conversion_intent']} - {brand_name}",
            "representative_question": f"{brand_name}{service}浠锋牸澶氬皯閽憋紵",
            "priority": 84,
            "questions": [
                f"{brand_name}{service}浠锋牸澶氬皯閽憋紵",
                f"{brand_name}{copy['process_question']}",
                f"{brand_name}鍦板潃鍜岃仈绯绘柟寮忔槸浠€涔堬紵",
                f"{brand_name}{copy['cycle_question']}",
                f"{brand_name}{copy['support_policy']}",
                f"{brand_name}瀹樼綉銆佸叕浼楀彿鎴栧鏈嶅叆鍙ｅ湪鍝噷锛?,
            ],
        },
    ]

    if fact_context:
        raw_groups[1]["questions"].append(f"{brand_name}{copy['public_material_question']}")

    return _coerce_question_groups(
        {"groups": raw_groups},
        forbidden_terms=get_industry_forbidden_terms(project.industry),
    )


def _coerce_question_groups(
    parsed: Dict[str, Any],
    forbidden_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    raw_groups = parsed.get("groups") or parsed.get("question_groups") or []
    if not isinstance(raw_groups, list):
        return []

    groups: List[Dict[str, Any]] = []
    seen_questions = set()
    total_questions = 0

    for idx, raw in enumerate(raw_groups):
        if not isinstance(raw, dict):
            continue
        intent_name = _clean_text(raw.get("intent_name") or raw.get("name") or raw.get("cluster") or f"闂缁?{idx + 1}", 180)
        layer = _normalize_layer(raw.get("layer"), intent_name)
        priority = _priority_to_int(raw.get("priority"), 80 if layer in {"pool_layer", "verification_layer"} else 70)
        questions: List[Dict[str, Any]] = []

        raw_questions = raw.get("questions") or raw.get("items") or []
        if isinstance(raw_questions, str):
            raw_questions = _split_terms(raw_questions)
        if not isinstance(raw_questions, list):
            raw_questions = []

        for item in raw_questions:
            if isinstance(item, dict):
                q_text = item.get("question_text") or item.get("text") or item.get("question") or item.get("query")
                q_priority = _priority_to_int(item.get("priority"), priority)
                sample_policy = _clean_text(item.get("sample_policy") or "mvp", 30) or "mvp"
                question_type = _clean_text(item.get("question_type") or item.get("type") or "brand_reputation", 100) or "brand_reputation"
                raw_tags = item.get("tags") or item.get("labels") or ""
                tags = "锛?.join(_split_terms(raw_tags)) if isinstance(raw_tags, str) else "锛?.join(str(tag) for tag in raw_tags[:8]) if isinstance(raw_tags, list) else ""
                focus = bool(item.get("focus") or item.get("important") or False)
                keyword_breakdown = _stringify_question_meta(item.get("keyword_breakdown") or item.get("keywords"), 1200)
                question_formula = _stringify_question_meta(item.get("question_formula") or item.get("formula"), 500)
                business_value = _stringify_question_meta(item.get("business_value") or item.get("commercial_value"), 100)
                evidence_support = _stringify_question_meta(item.get("evidence_support") or item.get("required_facts") or item.get("evidence_need"), 1200)
                content_actionability = _stringify_question_meta(item.get("content_actionability") or item.get("content_suggestion"), 1200)
                recommended_platforms = _stringify_question_meta(item.get("recommended_platforms") or item.get("platforms"), 500)
            else:
                q_text = item
                q_priority = priority
                sample_policy = "mvp"
                question_type = "brand_reputation"
                tags = ""
                focus = False
                keyword_breakdown = None
                question_formula = None
                business_value = None
                evidence_support = None
                content_actionability = None
                recommended_platforms = None
            q_text = _sanitize_generated_question_text(q_text, forbidden_terms=forbidden_terms)
            if not q_text or q_text in seen_questions:
                continue
            seen_questions.add(q_text)
            defaults = _default_question_meta(q_text, layer, tags)
            keyword_breakdown = keyword_breakdown or json.dumps({
                "question_terms": _split_terms(q_text),
                "tags": _split_terms(tags),
                "layer": layer,
            }, ensure_ascii=False)
            question_formula = question_formula or defaults["question_formula"]
            business_value = business_value or defaults["business_value"]
            evidence_support = evidence_support or defaults["evidence_support"]
            content_actionability = content_actionability or defaults["content_actionability"]
            recommended_platforms = recommended_platforms or defaults["recommended_platforms"]
            questions.append({
                "question_text": q_text,
                "question_type": question_type,
                "tags": tags,
                "keyword_breakdown": keyword_breakdown,
                "question_formula": question_formula,
                "business_value": business_value,
                "evidence_support": evidence_support,
                "content_actionability": content_actionability,
                "recommended_platforms": recommended_platforms,
                "priority": q_priority,
                "sample_policy": sample_policy,
                "enabled": True,
                "focus": focus,
            })
            total_questions += 1
            if len(questions) >= 8 or total_questions >= 36:
                break

        representative = _sanitize_generated_question_text(
            raw.get("representative_question"),
            forbidden_terms=forbidden_terms,
        )
        if not representative and questions:
            representative = questions[0]["question_text"]
        if not representative or not questions:
            continue
        groups.append({
            "layer": layer,
            "intent_name": intent_name,
            "representative_question": representative,
            "priority": priority,
            "questions": questions,
        })
        if len(groups) >= 6 or total_questions >= 36:
            break

    return groups


async def _generate_question_groups_with_llm(project, brand_name: str, facts: List[BrandFact]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    try:
        from app.llm.client import LLMClientFactory
        from app.llm.registry import get_model_registry

        registry = get_model_registry()
        config = registry.get_default_model()
        if not config:
            return None, "鏈厤缃彲鐢ㄧ殑澶фā鍨嬶紝宸蹭娇鐢ㄦ湰鍦扮煩闃垫ā鏉跨敓鎴?

        fact_context, credentials, _ = _extract_fact_context(facts, limit=36)
        service = _infer_service(project, brand_name, facts)
        archetype = get_question_archetype(project.industry)
        context = {
            "project_name": project.name,
            "brand_name": brand_name,
            "industry": _industry_label(project.industry),
            "region": project.region,
            "service_or_product": service,
            "industry_template": {
                "entity_label": archetype.get("entity_label"),
                "forbidden_terms": archetype.get("forbidden_terms") or [],
                "positive_examples": archetype.get("positive_examples") or [],
                "negative_examples": archetype.get("negative_examples") or [],
            },
            "excluded_ai_platform_terms": list(AI_PLATFORM_TERMS),
            "monitoring_ai_platform_note": "杩欎簺鏄娴嬪钩鍙?妯″瀷鍚嶇О锛屽彧鐢ㄤ簬鍚庣画鐩戞祴锛屼笉鏄敤鎴枫€佹湇鍔°€佸搧绫绘垨闂鍏抽敭璇嶏紱鐢熸垚闂鏃朵笉瑕佸啓鍏ラ棶棰樻枃鏈€?,
            "notes": project.notes,
            "known_facts": fact_context,
            "credential_clues": credentials,
        }
        prompt = f"""
浣犳槸 GEO/AIO 鐢熸垚寮忓紩鎿庝紭鍖栫殑闂鐭╅樀涓撳銆傝鍩轰簬椤圭洰璧勬枡鐢熸垚闂搴擄紝涓嶈鐢熸垚鏂囩珷銆?
鏍稿績閫昏緫鍙傝€冿細
1. 鍏堣鐩栫湡瀹炵敤鎴蜂細鍚?AI 鎻愰棶鐨勬悳绱㈡剰鍥撅紝鑰屼笉鏄満姊板叧閿瘝鍫嗗彔銆?2. 蹇呴』瑕嗙洊杩欎簺绨囷細鍝佺被鎺ㄨ崘/鍝佺墝鍏ユ睜銆佸彲淇￠獙璇併€佷环鏍?璐拱/鍜ㄨ/鎶ュ悕/閲囪喘鎵挎帴銆佷骇鍝佹垨鏈嶅姟鍖归厤銆佺珵鍝佸姣斻€佹渚嬪彛纰戙€佹斂绛栧悎瑙勩€?3. 鎸夊洓灞傜粍缁囷細pool_layer 鍏ユ睜灞傘€乿erification_layer 楠岃瘉/鍙ｇ灞傘€亀eight_layer 鏉冮噸灞傘€乧onversion_layer 杞寲/鎵挎帴灞傘€?4. 濡傛灉璧勬枡閲屾病鏈夋槑纭簨瀹烇紝鍙兘鍐欐垚鈥滄湁娌℃湁/濡備綍鏍搁獙/鎬庝箞鏍封€濈被闂锛屼笉瑕佹妸鏈‘璁ゅ唴瀹瑰啓鎴愪簨瀹炪€?5. 闂瑕佸儚鐪熷疄鐢ㄦ埛浼氶棶 AI 鐨勮嚜鐒惰瑷€锛岄伩鍏嶉噸澶嶁€滃摢瀹跺ソ 鎺ㄨ崘鈥濄€?6. 濡傛灉鏈夊煄甯?鍦板尯锛岃嚦灏戜竴鍗婇棶棰樿嚜鐒跺寘鍚湴鍖鸿瘝锛涘鏋滄湁鍝佺墝鍚嶏紝楠岃瘉灞傚拰杞寲灞傚繀椤诲寘鍚搧鐗屽悕銆?7. 涓嶈榛樿浣跨敤鍩硅琛屼笟璇嶏紝渚嬪鈥滆绋嬨€佹姤鍚嶃€佸鍛樸€侀€氳繃鐜囥€佸璁€佸笀璧勩€佹牎鍖衡€濓紱鍙湁椤圭洰璧勬枡鏄庣‘灞炰簬鍩硅/鏁欒偛鏃舵墠鍙娇鐢ㄣ€?8. 涓嶈鎶婃娴嬪钩鍙版垨妯″瀷鍚嶇О鍐欏叆闂鏂囨湰锛屼緥濡?DeepSeek銆並imi銆佽眴鍖呫€佹枃蹇冦€侀€氫箟銆丆hatGPT銆丟emini銆?
椤圭洰璧勬枡锛?{json.dumps(context, ensure_ascii=False, indent=2)}

璇峰彧杈撳嚭 JSON锛屼笉瑕?Markdown锛屼笉瑕佽В閲娿€傛牸寮忥細
{{
  "groups": [
    {{
      "layer": "pool_layer",
      "intent_name": "鏈湴鎺ㄨ崘/鍏ユ睜 - 鍝佺墝鍚?,
      "representative_question": "浠ｈ〃鎬ч棶棰?,
      "priority": 85,
      "questions": [
        {{"question_text": "鍏蜂綋闂", "priority": 85, "sample_policy": "mvp"}}
      ]
    }}
  ]
}}

鏁伴噺瑕佹眰锛氱敓鎴?5 涓棶棰樼粍锛屾瘡缁?5-7 涓棶棰橈紝鎬婚噺 25-35 涓€?"""
        prompt = render_prompt_template("geo/question_bank_v1.md", {
            "project_context_json": json.dumps(context, ensure_ascii=False, indent=2),
        })
        client = LLMClientFactory.create_client_from_config({
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "input_price_per_1k": config.input_price_per_1k,
            "output_price_per_1k": config.output_price_per_1k,
        })
        response = await client.chat(
            [
                {"role": "system", "content": "浣犲彧杈撳嚭鍙В鏋?JSON銆?},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=3600,
        )
        groups = _coerce_question_groups(
            _json_from_llm_text(response.content),
            forbidden_terms=archetype.get("forbidden_terms") or [],
        )
        if len(groups) >= 3 and sum(len(g["questions"]) for g in groups) >= 12:
            return groups, None
        return None, "澶фā鍨嬭繑鍥炵殑闂鐭╅樀鏁伴噺涓嶈冻锛屽凡浣跨敤鏈湴鐭╅樀妯℃澘鍏滃簳"
    except Exception as exc:
        return None, f"澶фā鍨嬬敓鎴愬け璐ワ紝宸蹭娇鐢ㄦ湰鍦扮煩闃垫ā鏉垮厹搴曪細{str(exc)[:180]}"


def _build_question_generation_strategy(project, brand_name: str, facts: List[BrandFact]) -> Dict[str, Any]:
    fact_context, credentials, _ = _extract_fact_context(facts, limit=36)
    service = _infer_service(project, brand_name, facts)
    credential_terms = []
    for item in credentials:
        for term in _split_terms(item):
            if term and term not in credential_terms:
                credential_terms.append(term)
    keyword_breakdown = {
        "brand_terms": [term for term in _split_terms(brand_name) if term],
        "geo_terms": [term for term in _split_terms(project.region) if term],
        "industry_terms": [term for term in _split_terms(_industry_label(project.industry)) if term],
        "service_terms": [term for term in _split_terms(service) if term],
        "credential_terms": credential_terms[:12],
        "fact_source_preview": fact_context[:500],
    }
    formulas = [
        {
            "layer": "pool_layer",
            "name": "鏈湴鍝佺被鎺ㄨ崘",
            "formula": "鍦板尯璇?+ 鏈嶅姟/鍝佺被璇?+ 鍝闈犺氨/鎺ㄨ崘/鎬庝箞閫?,
        },
        {
            "layer": "verification_layer",
            "name": "璧勮川涓庡彲淇℃牳楠?,
            "formula": "鍝佺墝璇?+ 璧勮川/璇佷功/缂栧彿/鍦板潃 + 鏄惁鐪熷疄/濡備綍鏍搁獙",
        },
        {
            "layer": "weight_layer",
            "name": "瀵规瘮涓庢潈閲嶆彁鍗?,
            "formula": "鍝佺墝璇?+ 绔炲搧/鍚岀被鏈烘瀯 + 浼樺娍/浠锋牸/妗堜緥/鍙ｇ瀵规瘮",
        },
        {
            "layer": "conversion_layer",
            "name": "杞寲鎵挎帴",
            "formula": "鍝佺墝璇?+ 浠锋牸/娴佺▼/鍦板潃/棰勭害/鍞悗 + 鍏蜂綋鎬庝箞鍋?,
        },
    ]
    return {
        "keyword_breakdown": keyword_breakdown,
        "question_formulas": formulas,
        "principle": "闂搴撲紭鍏堟ā鎷熺湡瀹炵敤鎴峰悜 AI 鎻愰棶鐨勮嚜鐒惰瑷€锛屽苟鎶婁簨瀹炲簱涓殑璧勮川銆佷骇鍝併€佸湴鍧€銆佷环鏍笺€佹渚嬬瓑鍙俊淇℃伅杞垚鍙娴嬬殑闂绾跨储銆?,
    }


@router.get("", response_model=List[ProjectOut])
async def list_projects(
    industry: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """鑾峰彇椤圭洰鍒楄〃"""
    service = ProjectService(db)
    projects = await service.list_projects(industry=industry, status=status, skip=skip, limit=limit)
    return projects


@router.post("", response_model=ProjectOut)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """鍒涘缓鏂伴」鐩?""
    service = ProjectService(db)
    project = await service.create_project(data)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """鑾峰彇椤圭洰璇︽儏"""
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """鏇存柊椤圭洰"""
    service = ProjectService(db)
    project = await service.update_project(project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """鍒犻櫎椤圭洰锛屽苟鍚屾鍒犻櫎璇ラ」鐩笅鐨勫叧鑱旀暟鎹€?""
    service = ProjectService(db)
    deleted = await service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted", "id": str(project_id)}


@router.post("/{project_id}/diagnose-gaps")
async def diagnose_gaps(
    project_id: UUID,
    provided_fields: List[str] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "strategist", "project_owner")),
):
    """璧勬枡缂哄彛璇婃柇"""
    service = ProjectService(db)
    result = await service.diagnose_gaps(project_id, provided_fields)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/diagnose-gaps-from-facts")
async def diagnose_gaps_from_facts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "strategist", "project_owner")),
):
    """鍩轰簬褰撳墠椤圭洰浜嬪疄搴撹嚜鍔ㄨ瘖鏂祫鏂欑己鍙ｏ紝骞惰繑鍥炶ˉ榻愬姩浣溿€?""
    service = ProjectService(db)
    result = await service.diagnose_gaps_from_facts(project_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/brands")
async def get_project_brands(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """鑾峰彇椤圭洰鍏宠仈鐨勫搧鐗屽垪琛?""
    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brands = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "project_id": str(b.project_id),
            "brand_name": b.brand_name,
            "company_name": b.company_name,
            "official_site": b.official_site,
            "description": b.description,
            "aliases": b.aliases,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        }
        for b in brands
    ]


@router.get("/{project_id}/brand-facts-summary")
async def get_brand_facts_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """鑾峰彇椤圭洰鍝佺墝浜嬪疄搴撴憳瑕?""
    service = ProjectService(db)
    result = await service.get_brand_facts_summary(project_id)
    return result


@router.get("/{project_id}/diagnosis-report")
async def get_project_diagnosis_report(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    鍩轰簬宸插綍鍏ユ娴嬫牱鏈敓鎴愬搧鐗?AI 浣撴銆佸洖绛旀ā寮忓拰绔炲搧宸窛鐨勮瀵熸姤鍛娿€?    璇ユ帴鍙ｅ彧鍋氬彲瑙ｉ噴鐨勬牱鏈綊绾筹紝涓嶅绉版帉鎻℃ā鍨嬪唴閮ㄦ帓搴忛€昏緫銆?    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    brands_result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brands = list(brands_result.scalars().all())
    brand_terms = _brand_terms(brands, project.name)

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(
            Brand.project_id == project_id,
            BrandFact.status == "confirmed",
            BrandFact.fact_scope == "public",
        )
    )
    public_facts = list(facts_result.scalars().all())

    samples_result = await db.execute(
        select(MonitoringSample, Question, QuestionGroup, MonitoringRun)
        .select_from(MonitoringSample)
        .join(Question, MonitoringSample.question_id == Question.id)
        .join(QuestionGroup, Question.group_id == QuestionGroup.id)
        .join(MonitoringRun, MonitoringSample.run_id == MonitoringRun.id)
        .where(MonitoringRun.project_id == project_id)
        .order_by(MonitoringSample.sampled_at.desc())
    )
    rows = samples_result.all()
    samples = [row[0] for row in rows]
    total = len(samples)
    mentioned = sum(1 for sample in samples if sample.brand_mentioned)
    recommended = sum(1 for sample in samples if sample.recommended)
    answer_texts = [sample.answer_text or "" for sample in samples if sample.answer_text]

    dimension_counts = {name: 0 for name in DIAGNOSIS_DIMENSION_PATTERNS}
    for text in answer_texts:
        for name, pattern in DIAGNOSIS_DIMENSION_PATTERNS.items():
            if re.search(pattern, text, flags=re.I):
                dimension_counts[name] += 1

    layer_summary: Dict[str, Dict[str, Any]] = {}
    for sample, question, group, run in rows:
        key = group.layer
        item = layer_summary.setdefault(key, {
            "layer": key,
            "layer_label": LAYER_LABELS.get(key, key),
            "sample_count": 0,
            "mentioned": 0,
            "recommended": 0,
            "questions": set(),
            "mechanisms": set(),
        })
        item["sample_count"] += 1
        item["mentioned"] += 1 if sample.brand_mentioned else 0
        item["recommended"] += 1 if sample.recommended else 0
        item["questions"].add(question.question_text)
        item["mechanisms"].add(run.mechanism_type)

    layer_items = []
    for item in layer_summary.values():
        sample_count = item["sample_count"]
        layer_items.append({
            "layer": item["layer"],
            "layer_label": item["layer_label"],
            "sample_count": sample_count,
            "mention_rate": _safe_rate(item["mentioned"], sample_count),
            "recommendation_rate": _safe_rate(item["recommended"], sample_count),
            "questions": sorted(item["questions"])[:8],
            "mechanisms": sorted(item["mechanisms"]),
        })

    mention_rate = _safe_rate(mentioned, total)
    recommendation_rate = _safe_rate(recommended, total)
    competitors = _extract_competitor_mentions(answer_texts, brand_terms)

    return {
        "project_id": str(project_id),
        "sample_count": total,
        "brand_health": {
            "brand_terms": brand_terms,
            "mentioned": mentioned,
            "recommended": recommended,
            "mention_rate": mention_rate,
            "recommendation_rate": recommendation_rate,
            "known_state": _derive_known_state(mention_rate, recommendation_rate),
            "public_confirmed_facts": len(public_facts),
        },
        "answer_pattern": {
            "dimension_counts": [
                {"dimension": name, "sample_hits": count}
                for name, count in sorted(dimension_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "layer_summary": layer_items,
            "source_signal": {
                "explicit_citations": sum(sample.explicit_citations for sample in samples),
                "inferred_source_matches": sum(sample.inferred_source_matches for sample in samples),
                "note": "鏄惧紡寮曠敤鍜屾帹瀹氬尮閰嶄笉鑳藉悎骞讹紝鍙兘鍒嗗埆瑙ｉ噴銆?,
            },
        },
        "competitor_gap": {
            "detected_competitors": competitors,
            "target_brand_mentions": mentioned,
            "note": "绔炲搧璇嗗埆鏉ヨ嚜鏍锋湰鏂囨湰涓殑瀹炰綋鎻愬彇锛屽睘浜庤瀵熺嚎绱紱姝ｅ紡鎶ュ憡闇€浜哄伐澶嶆牳绔炲搧鍚嶅崟銆?,
        },
        "actions": _diagnosis_actions(mention_rate, recommendation_rate, dimension_counts, len(public_facts)),
        "limitations": [
            "璇ヨ瘖鏂熀浜庣郴缁熷唴宸插綍鍏ユ牱鏈紝涓嶈兘浠ｈ〃鎵€鏈?AI 浜у搧闀挎湡琛ㄧ幇銆?,
            "鍥炵瓟妯″紡鍒嗘瀽鍙綊绾冲彲瑙傚療鏍锋湰锛屼笉澹扮О鎺屾彙妯″瀷鍐呴儴鎺掑簭閫昏緫銆?,
            "鏍锋湰鏁颁笉瓒虫椂锛岀粨鏋滃彧鑳戒綔涓哄垵姝ヨ瀵燂紝涓嶅簲鐢ㄤ綔楠屾敹缁撹銆?,
        ],
    }


@router.post("/{project_id}/generate-content-matrix")
async def generate_content_matrix(
    project_id: UUID,
    data: Optional[ContentMatrixRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("strategist", "project_owner")),
):
    """
    灏嗗綋鍓嶆湁鏁堥棶棰樼煩闃佃浆鎴愬唴瀹逛换鍔°€?    姣忎釜闂缁勭敓鎴愪竴涓彲鍐欎綔浠诲姟锛岄伩鍏嶉棶棰樺簱鍜屽唴瀹圭鐞嗕箣闂存柇閾俱€?    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    data = data or ContentMatrixRequest()

    groups_result = await db.execute(
        select(QuestionGroup)
        .where(
            QuestionGroup.project_id == project_id,
            QuestionGroup.status != "archived",
        )
        .order_by(QuestionGroup.priority.desc(), QuestionGroup.created_at.desc())
        .limit(data.max_tasks)
    )
    groups = list(groups_result.scalars().all())
    if not groups:
        raise HTTPException(status_code=400, detail="褰撳墠椤圭洰杩樻病鏈夊彲鐢ㄧ殑闂鐭╅樀锛岃鍏堢敓鎴愰棶棰樺簱")

    cancelled_tasks = 0
    if data.replace_existing:
        existing_result = await db.execute(
            select(ContentTask).where(
                ContentTask.project_id == project_id,
                ContentTask.status.in_(["draft", "in_progress", "review", "rework", "approved"]),
            )
        )
        for task in existing_result.scalars().all():
            task.status = "cancelled"
            cancelled_tasks += 1
        if cancelled_tasks:
            await db.flush()

    existing_result = await db.execute(
        select(ContentTask).where(
            ContentTask.project_id == project_id,
            ContentTask.status != "cancelled",
        )
    )
    existing_keys = {
        (str(task.group_id), task.content_type, task.layer)
        for task in existing_result.scalars().all()
        if task.group_id
    }

    created_tasks: List[ContentTask] = []
    skipped_tasks = 0
    schedule_start = _normalize_schedule_start(data.start_date)
    layer_schedule_counts: dict[str, int] = defaultdict(int)
    for group in groups:
        content_type = _content_type_for_group(group)
        key = (str(group.id), content_type, group.layer)
        if key in existing_keys:
            skipped_tasks += 1
            continue
        priority = _task_priority(group.priority or 0)
        cost_preset = _task_cost_preset(content_type, priority)
        due_date = None
        if data.apply_schedule:
            layer_index = layer_schedule_counts[group.layer]
            layer_schedule_counts[group.layer] += 1
            due_date = schedule_start + timedelta(
                days=LAYER_SCHEDULE_OFFSETS.get(group.layer, 10) + layer_index * 2
            )
        task = ContentTask(
            project_id=project_id,
            group_id=group.id,
            content_type=content_type,
            layer=group.layer,
            priority=priority,
            status="draft",
            due_date=due_date,
            estimated_token_cost=cost_preset["tokens"],
            estimated_api_cost=cost_preset["api"],
            estimated_labor_minutes=cost_preset["labor"],
        )
        db.add(task)
        created_tasks.append(task)
        existing_keys.add(key)

    await db.commit()
    for task in created_tasks:
        await db.refresh(task)

    content_matrix = [
        {
            "layer": task.layer,
            "content_type": task.content_type,
            "priority": task.priority,
            "estimated_articles": 1,
        }
        for task in created_tasks
    ]
    budget_summary = StrategyAgent().estimate_budget(content_matrix, article_count=len(created_tasks)) if created_tasks else None

    return {
        "project_id": str(project_id),
        "source_groups": len(groups),
        "created_tasks": len(created_tasks),
        "skipped_tasks": skipped_tasks,
        "cancelled_tasks": cancelled_tasks,
        "schedule": {
            "applied": data.apply_schedule,
            "start_date": schedule_start.isoformat(),
            "first_due_date": min((task.due_date for task in created_tasks if task.due_date), default=None).isoformat()
            if any(task.due_date for task in created_tasks) else None,
            "last_due_date": max((task.due_date for task in created_tasks if task.due_date), default=None).isoformat()
            if any(task.due_date for task in created_tasks) else None,
        },
        "budget_estimate": budget_summary,
        "tasks": [
            {
                "id": str(task.id),
                "group_id": str(task.group_id) if task.group_id else None,
                "content_type": task.content_type,
                "layer": task.layer,
                "priority": task.priority,
                "status": task.status,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "estimated_token_cost": float(task.estimated_token_cost) if task.estimated_token_cost is not None else None,
                "estimated_api_cost": float(task.estimated_api_cost) if task.estimated_api_cost is not None else None,
                "estimated_labor_minutes": float(task.estimated_labor_minutes) if task.estimated_labor_minutes is not None else None,
            }
            for task in created_tasks
        ],
    }


@router.post("/{project_id}/generate-question-bank", dependencies=[Depends(require_roles("strategist", "project_owner"))])
async def generate_question_bank(
    project_id: UUID,
    brand_name: Optional[str] = None,
    replace_existing: bool = Query(True, description="閲嶆柊鐢熸垚鏃跺綊妗ｆ棫闂鐭╅樀锛岄伩鍏嶉噸澶嶇疮鍔?),
    db: AsyncSession = Depends(get_db)
):
    """
    鐢熸垚 GEO 闂鐭╅樀銆?    浼樺厛浣跨敤鐢ㄦ埛閰嶇疆鐨勫ぇ妯″瀷鐢熸垚锛涙病鏈夊彲鐢ㄦā鍨嬫垨妯″瀷澶辫触鏃讹紝浣跨敤鍘熼」鐩悓婧愮殑纭畾鎬х煩闃垫ā鏉垮厹搴曘€?    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    brand_result = await db.execute(
        select(Brand).where(Brand.project_id == project_id).order_by(Brand.created_at.asc())
    )
    brands = list(brand_result.scalars().all())
    primary_brand = brands[0] if brands else None
    effective_brand_name = (
        brand_name
        or (primary_brand.brand_name if primary_brand else None)
        or project.name
        or "璇ュ搧鐗?
    )

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(Brand.project_id == project_id)
        .order_by(BrandFact.created_at.desc())
        .limit(120)
    )
    facts = list(facts_result.scalars().all())

    generated_groups, fallback_reason = await _generate_question_groups_with_llm(
        project,
        effective_brand_name,
        facts,
    )
    source = "llm"
    if not generated_groups:
        generated_groups = _build_template_groups(project, effective_brand_name, facts)
        source = "template"

    if not generated_groups:
        raise HTTPException(status_code=500, detail="Failed to generate question bank")

    archived_groups = 0
    if replace_existing:
        existing_result = await db.execute(
            select(QuestionGroup).where(
                QuestionGroup.project_id == project_id,
                QuestionGroup.status != "archived",
            )
        )
        existing_groups = list(existing_result.scalars().all())
        for group in existing_groups:
            group.status = "archived"
        archived_groups = len(existing_groups)
        if archived_groups:
            await db.flush()

    created_groups: List[QuestionGroup] = []
    created_questions: List[Question] = []

    for group_data in generated_groups:
        group = QuestionGroup(
            project_id=project_id,
            layer=group_data["layer"],
            intent_name=group_data["intent_name"],
            representative_question=group_data["representative_question"],
            priority=group_data["priority"],
            status="active",
        )
        db.add(group)
        await db.flush()

        for question_data in group_data["questions"]:
            question = Question(
                group_id=group.id,
                question_text=question_data["question_text"],
                question_type=question_data.get("question_type") or "brand_reputation",
                tags=question_data.get("tags"),
                keyword_breakdown=question_data.get("keyword_breakdown"),
                question_formula=question_data.get("question_formula"),
                business_value=question_data.get("business_value"),
                evidence_support=question_data.get("evidence_support"),
                content_actionability=question_data.get("content_actionability"),
                recommended_platforms=question_data.get("recommended_platforms"),
                priority=question_data["priority"],
                sample_policy=question_data["sample_policy"],
                enabled=question_data.get("enabled", True),
                focus=question_data.get("focus", False),
            )
            db.add(question)
            created_questions.append(question)

        created_groups.append(group)

    await db.commit()

    for group in created_groups:
        await db.refresh(group)
    for question in created_questions:
        await db.refresh(question)

    group_ids = [g.id for g in created_groups]
    result = await db.execute(
        select(QuestionGroup)
        .where(QuestionGroup.id.in_(group_ids))
        .options(selectinload(QuestionGroup.questions))
    )
    groups_with_questions = {g.id: g for g in result.scalars().all()}

    return {
        "project_id": str(project_id),
        "brand_name": effective_brand_name,
        "replace_existing": replace_existing,
        "archived_groups": archived_groups,
        "source": source,
        "fallback_reason": fallback_reason,
        "generation_strategy": _build_question_generation_strategy(project, effective_brand_name, facts),
        "generated_groups": len(created_groups),
        "generated_questions": len(created_questions),
        "groups": [
            {
                "id": str(g.id),
                "layer": g.layer,
                "layer_label": LAYER_LABELS.get(g.layer, g.layer),
                "intent_name": g.intent_name,
                "representative_question": g.representative_question,
                "priority": g.priority,
                "questions": [
                    {
                        "id": str(q.id),
                        "question_text": q.question_text,
                        "question_type": q.question_type,
                        "tags": q.tags,
                        "keyword_breakdown": q.keyword_breakdown,
                        "question_formula": q.question_formula,
                        "business_value": q.business_value,
                        "evidence_support": q.evidence_support,
                        "content_actionability": q.content_actionability,
                        "recommended_platforms": q.recommended_platforms,
                        "priority": q.priority,
                        "sample_policy": q.sample_policy,
                    }
                    for q in groups_with_questions.get(g.id, g).questions
                ],
            }
            for g in created_groups
        ],
    }
