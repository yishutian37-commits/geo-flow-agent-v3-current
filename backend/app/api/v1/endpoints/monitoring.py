import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.models.brand import Brand
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.project import Project
from app.models.question import Question
from app.models.source_asset import SourceAsset
from app.services.monitoring_service import MonitoringService
from app.services.webbridge_service import WebBridgeError, WebBridgeService

router = APIRouter()


class WebBridgeSampleRequest(BaseModel):
    question_id: UUID
    wait_seconds: int = Field(default=60, ge=15, le=300)
    create_sample: bool = True


class MonitoringRunStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(running|completed|failed|cancelled)$")


def _run_to_dict(run, sample_count: int = 0, target_names: Optional[dict[str, str]] = None) -> dict:
    """将MonitoringRun ORM对象转为可JSON序列化的字典"""
    target_id = str(run.model_target_id) if run.model_target_id else None
    return {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "run_type": run.run_type,
        "mechanism_type": run.mechanism_type,
        "model_target_id": target_id,
        "model_target_name": (target_names or {}).get(target_id),
        "call_mode_detail": run.call_mode_detail,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "sample_policy": run.sample_policy,
        "status": run.status,
        "sample_count": sample_count,
        "estimated_api_cost": float(run.estimated_api_cost) if run.estimated_api_cost else None,
        "actual_api_cost": float(run.actual_api_cost) if run.actual_api_cost else None,
    }


def _source_relation_label(category: str) -> str:
    return {
        "owned_asset": "自有信源",
        "authority": "权威来源",
        "search_engine": "搜索中转",
        "media_platform": "媒体/社区",
        "third_party": "第三方来源",
        "unknown": "未知来源",
    }.get(category, "未知来源")


def _classify_source(source: dict, source_assets: Optional[list[SourceAsset]] = None) -> dict:
    source_assets = source_assets or []
    url = str(source.get("url") or "").strip()
    domain = _domain_from_url(url)
    matched_asset = None
    for asset in source_assets:
        asset_domain = _domain_from_url(asset.url)
        if asset_domain and domain and (domain == asset_domain or domain.endswith(f".{asset_domain}")):
            matched_asset = asset
            break

    if matched_asset:
        category = "owned_asset"
    elif any(key in domain for key in ["baidu.", "bing.", "google.", "sogou.", "so.com", "sm.cn"]):
        category = "search_engine"
    elif domain.endswith(".gov.cn") or domain.endswith(".edu.cn") or ".gov." in domain or ".edu." in domain:
        category = "authority"
    elif any(key in domain for key in [
        "mp.weixin.qq.com", "baijiahao.baidu.com", "toutiao.com", "zhihu.com",
        "xiaohongshu.com", "sohu.com", "sina.com", "qq.com", "163.com",
    ]):
        category = "media_platform"
    elif domain:
        category = "third_party"
    else:
        category = "unknown"

    enriched = dict(source)
    enriched.update({
        "domain": domain,
        "category": category,
        "category_label": _source_relation_label(category),
        "is_own_asset": category == "owned_asset",
        "matched_source_asset_id": str(matched_asset.id) if matched_asset else None,
        "matched_source_asset_type": matched_asset.source_type if matched_asset else None,
        "matched_source_asset_platform": matched_asset.platform if matched_asset else None,
    })
    return enriched


def _normalize_sources(raw_sources, source_assets: Optional[list[SourceAsset]] = None) -> list[dict]:
    if not isinstance(raw_sources, list):
        return []
    normalized = []
    seen = set()
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(_classify_source(item, source_assets))
    return normalized


def _sample_to_dict(sample, source_assets: Optional[list[SourceAsset]] = None) -> dict:
    try:
        sources = json.loads(sample.sources_json or "[]")
    except (TypeError, json.JSONDecodeError):
        sources = []
    try:
        analysis = json.loads(sample.analysis_json or "{}")
    except (TypeError, json.JSONDecodeError):
        analysis = {}
    normalized_sources = _normalize_sources(sources, source_assets)
    return {
        "id": str(sample.id),
        "run_id": str(sample.run_id),
        "question_id": str(sample.question_id),
        "answer_text": sample.answer_text,
        "brand_mentioned": sample.brand_mentioned,
        "recommended": sample.recommended,
        "position": sample.position,
        "list_length": sample.list_length,
        "visibility_score": float(sample.visibility_score) if sample.visibility_score is not None else None,
        "explicit_citations": sample.explicit_citations,
        "inferred_source_matches": sample.inferred_source_matches,
        "sources": normalized_sources,
        "source_count": len(normalized_sources),
        "analysis": analysis if isinstance(analysis, dict) else {},
        "screenshot_url": sample.screenshot_url,
        "sampled_at": sample.sampled_at.isoformat() if sample.sampled_at else None,
    }


def _sample_row_to_dict(sample, run=None, question=None, target=None, project=None, source_assets: Optional[list[SourceAsset]] = None) -> dict:
    data = _sample_to_dict(sample, source_assets)
    data.update({
        "project_id": str(run.project_id) if run else None,
        "project_name": project.name if project else None,
        "run_type": run.run_type if run else None,
        "run_status": run.status if run else None,
        "mechanism_type": run.mechanism_type if run else None,
        "model_target_id": str(run.model_target_id) if run and run.model_target_id else None,
        "model_target_name": target.product_name if target else None,
        "question_text": question.question_text if question else None,
        "question_priority": question.priority if question else None,
        "sample_policy": question.sample_policy if question else None,
    })
    return data


async def _sample_counts(db: AsyncSession, run_ids: list[str]) -> dict[str, int]:
    if not run_ids:
        return {}
    result = await db.execute(
        select(MonitoringSample.run_id, func.count(MonitoringSample.id))
        .where(MonitoringSample.run_id.in_(run_ids))
        .group_by(MonitoringSample.run_id)
    )
    return {str(run_id): count for run_id, count in result.all()}


def _split_aliases(value: Optional[str]) -> list[str]:
    return [item.strip() for item in re.split(r"[,，、/;；\n\r]+", value or "") if item.strip()]


def _brand_terms(project: Optional[Project], brands: list[Brand]) -> list[str]:
    terms = [project.name if project else ""]
    for brand in brands:
        terms.extend([brand.brand_name, brand.company_name or ""])
        terms.extend(_split_aliases(brand.aliases))
    seen = []
    for term in terms:
        term = str(term or "").strip()
        if term and term not in seen:
            seen.append(term)
    return seen


def _domain_from_url(url: Optional[str]) -> str:
    try:
        parsed = urlparse(url or "")
        return parsed.netloc.replace("www.", "")
    except Exception:
        return ""


def _infer_answer_metrics(answer_text: str, brand_terms: list[str], source_assets: list[SourceAsset]) -> dict:
    answer = answer_text or ""
    matched_brand_terms = [term for term in brand_terms if term and term in answer]
    brand_mentioned = bool(matched_brand_terms)
    recommendation_pattern = r"推荐|靠谱|值得|优先|适合|建议选择|可以选择|首选|认可|口碑较好|通过率|recommend|recommended|good choice"
    negative_pattern = r"不推荐|不建议|差评|投诉|虚假|夸大|黑名单|风险|骗局|不靠谱|谨慎|避坑|负面|处罚|违法|problem|risk|scam"
    risk_pattern = r"无法核实|未查询到|信息不足|没有公开|需核验|建议核实|可能|疑似|不确定"
    recommendation_hits = sorted(set(re.findall(recommendation_pattern, answer, flags=re.I)))
    negative_hits = sorted(set(re.findall(negative_pattern, answer, flags=re.I)))
    risk_hits = sorted(set(re.findall(risk_pattern, answer, flags=re.I)))
    recommended = bool(brand_mentioned and recommendation_hits and not negative_hits)
    explicit_citations = len(re.findall(r"https?://[^\s)）】]+", answer))
    inferred_matches = 0
    for asset in source_assets:
        domain = _domain_from_url(asset.url)
        platform = asset.platform or ""
        if domain and domain in answer:
            inferred_matches += 1
            continue
        if platform and len(platform) >= 2 and platform in answer:
            inferred_matches += 1
    if negative_hits:
        sentiment = "negative"
        sentiment_label = "负面/风险"
    elif recommended:
        sentiment = "positive"
        sentiment_label = "正向推荐"
    elif brand_mentioned:
        sentiment = "neutral"
        sentiment_label = "中性提及"
    else:
        sentiment = "unknown"
        sentiment_label = "未识别品牌"

    basis = []
    if matched_brand_terms:
        basis.append(f"命中品牌词：{', '.join(matched_brand_terms[:5])}")
    else:
        basis.append("回答中未命中品牌词或品牌别名")
    if recommendation_hits:
        basis.append(f"命中推荐词：{', '.join(recommendation_hits[:8])}")
    if negative_hits:
        basis.append(f"命中负面/风险词：{', '.join(negative_hits[:8])}")
    if risk_hits:
        basis.append(f"存在需人工核验表述：{', '.join(risk_hits[:8])}")
    if explicit_citations:
        basis.append(f"回答文本中识别到 {explicit_citations} 个显式链接")
    if inferred_matches:
        basis.append(f"回答文本与 {inferred_matches} 个信源资产存在匹配")

    return {
        "brand_mentioned": brand_mentioned,
        "recommended": recommended,
        "explicit_citations": explicit_citations,
        "inferred_source_matches": inferred_matches,
        "analysis": {
            "matched_brand_terms": matched_brand_terms[:10],
            "recommendation_keywords": recommendation_hits[:12],
            "negative_keywords": negative_hits[:12],
            "risk_keywords": risk_hits[:12],
            "sentiment": sentiment,
            "sentiment_label": sentiment_label,
            "judgment_basis": basis,
            "recommendation_judgment": "已推荐" if recommended else "已提及但未明确推荐" if brand_mentioned else "未提及品牌",
            "review_required": bool(negative_hits or risk_hits),
        },
    }


@router.get("/webbridge/status")
async def get_webbridge_status():
    """检查 Kimi WebBridge 后台服务和浏览器扩展连接状态。"""
    bridge = WebBridgeService()
    try:
        status = await bridge.get_status()
    except WebBridgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    daemon_version = str(status.get("version") or "").lstrip("v")
    extension_version = str(status.get("extension_version") or "").lstrip("v")
    version_matched = bool(daemon_version and extension_version and daemon_version == extension_version)
    provider = status.get("bridge_provider") or "kimi"
    warning = None
    if provider == "qweb" and not status.get("extension_connected"):
        extension_path = status.get("extension_path") or "应用资源目录中的 qwebbridge/extension"
        warning = f"QWebBridge 后台已集成并启动，但浏览器扩展尚未连接。请在 Chrome/Edge 加载扩展目录：{extension_path}"
    elif provider == "kimi" and not version_matched:
        warning = "Kimi WebBridge 后台服务版本与浏览器扩展版本不一致，建议更新浏览器扩展后再检测。"
    return {
        **status,
        "version_matched": version_matched,
        "warning": warning,
    }


@router.get("/screenshots/{filename}")
async def get_monitoring_screenshot(filename: str):
    """读取 WebBridge 自动检测保存的回答截图。"""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(status_code=400, detail="Invalid screenshot filename")
    storage_dir = Path(os.getenv("GEO_SCREENSHOT_DIR") or Path.cwd() / "monitoring_screenshots")
    file_path = storage_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(file_path)


@router.get("/runs")
async def list_monitoring_runs(
    project_id: Optional[UUID] = Query(None),
    mechanism_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """获取检测记录列表"""
    service = MonitoringService(db)
    runs = await service.list_runs(
        project_id=project_id,
        mechanism_type=mechanism_type,
        status=status,
        skip=skip,
        limit=limit,
    )
    counts = await _sample_counts(db, [str(run.id) for run in runs])
    target_ids = [str(run.model_target_id) for run in runs if run.model_target_id]
    target_names = {}
    if target_ids:
        target_result = await db.execute(select(ModelTarget).where(ModelTarget.id.in_(target_ids)))
        target_names = {str(target.id): target.product_name for target in target_result.scalars().all()}
    return [_run_to_dict(r, counts.get(str(r.id), 0), target_names) for r in runs]


@router.get("/samples")
async def list_monitoring_samples(
    project_id: Optional[UUID] = Query(None),
    run_id: Optional[UUID] = Query(None),
    model_target_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MonitoringSample, MonitoringRun, Question, ModelTarget, Project)
        .join(MonitoringRun, MonitoringSample.run_id == MonitoringRun.id)
        .join(Question, MonitoringSample.question_id == Question.id)
        .join(ModelTarget, MonitoringRun.model_target_id == ModelTarget.id, isouter=True)
        .join(Project, MonitoringRun.project_id == Project.id, isouter=True)
    )
    if project_id:
        query = query.where(MonitoringRun.project_id == project_id)
    if run_id:
        query = query.where(MonitoringSample.run_id == run_id)
    if model_target_id:
        query = query.where(MonitoringRun.model_target_id == model_target_id)
    query = query.order_by(MonitoringSample.sampled_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    project_ids = {
        str(run.project_id)
        for _, run, _, _, _ in result.all()
        if run and run.project_id
    }
    result = await db.execute(query)
    source_assets_by_project: dict[str, list[SourceAsset]] = defaultdict(list)
    if project_ids:
        assets_result = await db.execute(
            select(SourceAsset).where(SourceAsset.project_id.in_(project_ids), SourceAsset.status == "active")
        )
        for asset in assets_result.scalars().all():
            source_assets_by_project[str(asset.project_id)].append(asset)
    return [
        _sample_row_to_dict(
            sample,
            run=run,
            question=question,
            target=target,
            project=project,
            source_assets=source_assets_by_project.get(str(run.project_id), []) if run else [],
        )
        for sample, run, question, target, project in result.all()
    ]


@router.delete("/samples/{sample_id}")
async def delete_monitoring_sample(
    sample_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除单条检测明细样本，不删除整次检测记录。"""
    service = MonitoringService(db)
    deleted = await service.delete_sample(sample_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Monitoring sample not found")
    return {"message": "Monitoring sample deleted", **deleted}


@router.get("/source-analysis")
async def get_source_analysis(
    project_id: UUID,
    run_id: Optional[UUID] = Query(None),
    model_target_id: Optional[UUID] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    assets_result = await db.execute(
        select(SourceAsset).where(SourceAsset.project_id == project_id, SourceAsset.status == "active")
    )
    source_assets = list(assets_result.scalars().all())

    query = (
        select(MonitoringSample, MonitoringRun, ModelTarget)
        .join(MonitoringRun, MonitoringSample.run_id == MonitoringRun.id)
        .join(ModelTarget, MonitoringRun.model_target_id == ModelTarget.id, isouter=True)
        .where(MonitoringRun.project_id == project_id)
        .order_by(MonitoringSample.sampled_at.desc())
        .limit(limit)
    )
    if run_id:
        query = query.where(MonitoringSample.run_id == run_id)
    if model_target_id:
        query = query.where(MonitoringRun.model_target_id == model_target_id)

    result = await db.execute(query)
    rows = list(result.all())

    category_counts: Counter[str] = Counter()
    domain_stats: dict[str, dict] = {}
    platform_stats: dict[str, dict] = {}
    sample_count = len(rows)
    samples_with_sources = 0
    total_sources = 0

    for sample, run, target in rows:
        sample_data = _sample_to_dict(sample, source_assets)
        sources = sample_data.get("sources") or []
        platform_name = target.product_name if target else "未知平台"
        platform_item = platform_stats.setdefault(platform_name, {
            "platform": platform_name,
            "sample_count": 0,
            "samples_with_sources": 0,
            "total_sources": 0,
            "owned_asset_sources": 0,
            "authority_sources": 0,
            "recommended_count": 0,
            "mentioned_count": 0,
        })
        platform_item["sample_count"] += 1
        if sample.recommended:
            platform_item["recommended_count"] += 1
        if sample.brand_mentioned:
            platform_item["mentioned_count"] += 1
        if sources:
            samples_with_sources += 1
            platform_item["samples_with_sources"] += 1

        for source in sources:
            total_sources += 1
            platform_item["total_sources"] += 1
            category = source.get("category") or "unknown"
            domain = source.get("domain") or "unknown"
            category_counts[category] += 1
            if category == "owned_asset":
                platform_item["owned_asset_sources"] += 1
            if category == "authority":
                platform_item["authority_sources"] += 1
            domain_item = domain_stats.setdefault(domain, {
                "domain": domain,
                "count": 0,
                "category": category,
                "category_label": _source_relation_label(category),
                "is_own_asset": category == "owned_asset",
            })
            domain_item["count"] += 1

    owned_asset_sources = category_counts.get("owned_asset", 0)
    authority_sources = category_counts.get("authority", 0)
    search_engine_sources = category_counts.get("search_engine", 0)
    third_party_sources = category_counts.get("third_party", 0)
    source_coverage_rate = round(samples_with_sources / sample_count * 100, 1) if sample_count else 0
    owned_asset_rate = round(owned_asset_sources / total_sources * 100, 1) if total_sources else 0

    suggestions = []
    if sample_count and samples_with_sources == 0:
        suggestions.append("本批检测没有抓到任何来源链接，优先确认目标 AI 平台是否开启联网/引用展示。")
    if total_sources and owned_asset_sources == 0:
        suggestions.append("AI 已引用外部页面，但没有引用你的自有信源；建议补充官网、资质页、案例页、公众号文章等可公开访问资产。")
    if search_engine_sources > owned_asset_sources:
        suggestions.append("搜索中转页占比偏高，说明 AI 可能依赖搜索结果页而非稳定内容资产；建议建设更明确的落地页和权威资料页。")
    if authority_sources > 0 and owned_asset_sources == 0:
        suggestions.append("已有权威来源被引用，可以围绕这些权威信息制作品牌解释页，争取让 AI 同时引用品牌自有页面。")
    if not suggestions:
        suggestions.append("来源结构暂时可用，下一步可以重点提升自有信源的覆盖率和被引用次数。")

    return {
        "project_id": str(project_id),
        "sample_count": sample_count,
        "samples_with_sources": samples_with_sources,
        "samples_without_sources": max(sample_count - samples_with_sources, 0),
        "source_coverage_rate": source_coverage_rate,
        "total_sources": total_sources,
        "owned_asset_sources": owned_asset_sources,
        "owned_asset_rate": owned_asset_rate,
        "authority_sources": authority_sources,
        "search_engine_sources": search_engine_sources,
        "third_party_sources": third_party_sources,
        "source_assets_configured": len(source_assets),
        "category_counts": [
            {
                "category": category,
                "label": _source_relation_label(category),
                "count": count,
            }
            for category, count in category_counts.most_common()
        ],
        "top_domains": sorted(domain_stats.values(), key=lambda item: item["count"], reverse=True)[:12],
        "platform_stats": sorted(platform_stats.values(), key=lambda item: item["sample_count"], reverse=True),
        "suggestions": suggestions,
    }


@router.post("/runs")
async def create_monitoring_run(
    project_id: UUID,
    run_type: str,
    mechanism_type: str,
    model_target_id: Optional[UUID] = None,
    sample_policy: str = "mvp",
    call_mode_detail: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """创建检测记录"""
    service = MonitoringService(db)
    try:
        run = await service.create_run(
            project_id=project_id,
            run_type=run_type,
            mechanism_type=mechanism_type,
            model_target_id=model_target_id,
            sample_policy=sample_policy,
            call_mode_detail=call_mode_detail,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _run_to_dict(run, 0)


@router.get("/runs/{run_id}")
async def get_monitoring_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取检测记录"""
    service = MonitoringService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Monitoring run not found")
    counts = await _sample_counts(db, [str(run.id)])
    return _run_to_dict(run, counts.get(str(run.id), 0))


@router.delete("/runs/{run_id}")
async def delete_monitoring_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """删除检测记录，并级联删除该记录下的检测样本与舆情记录。"""
    service = MonitoringService(db)
    deleted = await service.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Monitoring run not found")
    return {"message": "Monitoring run deleted", **deleted}


@router.post("/runs/{run_id}/status")
async def update_monitoring_run_status(
    run_id: UUID,
    data: MonitoringRunStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """前端停止/异常时显式收口检测记录状态。"""
    service = MonitoringService(db)
    try:
        run = await service.update_run_status(run_id, data.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    counts = await _sample_counts(db, [str(run.id)])
    return _run_to_dict(run, counts.get(str(run.id), 0))


@router.post("/runs/{run_id}/samples")
async def add_sample(
    run_id: UUID,
    question_id: UUID,
    answer_text: Optional[str] = None,
    brand_mentioned: bool = False,
    recommended: bool = False,
    position: Optional[int] = None,
    list_length: Optional[int] = None,
    explicit_citations: int = 0,
    inferred_source_matches: int = 0,
    screenshot_url: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """添加检测样本"""
    service = MonitoringService(db)
    try:
        sample = await service.add_sample(
            run_id=run_id,
            question_id=question_id,
            answer_text=answer_text,
            brand_mentioned=brand_mentioned,
            recommended=recommended,
            position=position,
            list_length=list_length,
            explicit_citations=explicit_citations,
            inferred_source_matches=inferred_source_matches,
            screenshot_url=screenshot_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _sample_to_dict(sample)


@router.post("/runs/{run_id}/webbridge-sample")
async def ask_with_webbridge(
    run_id: UUID,
    data: WebBridgeSampleRequest,
    db: AsyncSession = Depends(get_db),
):
    """通过 Kimi WebBridge 打开检测平台网页版，自动提问并可写入检测样本。"""
    service = MonitoringService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Monitoring run not found")

    target_result = await db.execute(select(ModelTarget).where(ModelTarget.id == run.model_target_id))
    target = target_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=400, detail="该检测记录没有可用的检测平台")

    question_result = await db.execute(select(Question).where(Question.id == data.question_id))
    question = question_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=400, detail="Question not found")

    project_result = await db.execute(select(Project).where(Project.id == run.project_id))
    project = project_result.scalar_one_or_none()
    brands_result = await db.execute(select(Brand).where(Brand.project_id == run.project_id))
    brands = list(brands_result.scalars().all())
    source_result = await db.execute(select(SourceAsset).where(SourceAsset.project_id == run.project_id, SourceAsset.status == "active"))
    source_assets = list(source_result.scalars().all())

    bridge = WebBridgeService()
    try:
        answer = await bridge.ask_question(
            target=target,
            question=question.question_text,
            session=f"geo-monitor-{run_id}",
            wait_seconds=data.wait_seconds,
        )
    except WebBridgeError as exc:
        await service.update_run_status(run_id, "failed")
        raise HTTPException(status_code=400, detail=str(exc))

    answer_sources = answer.sources or []
    brand_terms = _brand_terms(project, brands)
    mention_evidence = await bridge.capture_mention_evidence(
        session=answer.session,
        brand_terms=brand_terms,
        answer_text=answer.answer_text,
        selector=target.response_selector,
    )
    metric_answer_text = answer.answer_text
    if mention_evidence and mention_evidence.get("evidence_text") and mention_evidence.get("evidence_text") not in metric_answer_text:
        metric_answer_text = f"{mention_evidence.get('evidence_text')}\n{metric_answer_text or ''}".strip()
    inferred = _infer_answer_metrics(metric_answer_text, brand_terms, source_assets)
    if mention_evidence:
        analysis = inferred.setdefault("analysis", {})
        analysis["mention_evidence"] = mention_evidence
        matched_term = mention_evidence.get("matched_term")
        if matched_term:
            matched_terms = analysis.setdefault("matched_brand_terms", [])
            if matched_term not in matched_terms:
                matched_terms.insert(0, matched_term)
        basis = analysis.setdefault("judgment_basis", [])
        basis.append(
            f"已定位品牌提及证据：{matched_term or '品牌词'}，截图优先保存提及位置"
        )
        if mention_evidence.get("screenshot_url"):
            answer.screenshot_url = mention_evidence["screenshot_url"]
    if answer_sources:
        inferred["explicit_citations"] = max(inferred.get("explicit_citations") or 0, len(answer_sources))
        inferred.setdefault("analysis", {}).setdefault("judgment_basis", []).append(f"回答区域抓取到 {len(answer_sources)} 条信息来源链接")
        matched_domains = {
            _domain_from_url(item.get("url"))
            for item in answer_sources
            if isinstance(item, dict) and item.get("url")
        }
        own_asset_matches = sum(
            1
            for asset in source_assets
            if _domain_from_url(asset.url) and _domain_from_url(asset.url) in matched_domains
        )
        inferred["inferred_source_matches"] = max(inferred.get("inferred_source_matches") or 0, own_asset_matches)
        if own_asset_matches:
            inferred.setdefault("analysis", {}).setdefault("judgment_basis", []).append(f"来源中匹配到 {own_asset_matches} 个自有信源资产")
    sample_data = None
    if data.create_sample:
        try:
            sample = await service.add_sample(
                run_id=run_id,
                question_id=data.question_id,
                answer_text=answer.answer_text,
                brand_mentioned=inferred["brand_mentioned"],
                recommended=inferred["recommended"],
                explicit_citations=inferred["explicit_citations"],
                inferred_source_matches=inferred["inferred_source_matches"],
                screenshot_url=answer.screenshot_url,
                sources=answer_sources,
                analysis=inferred.get("analysis") or {},
            )
        except ValueError as exc:
            await service.update_run_status(run_id, "failed")
            raise HTTPException(status_code=400, detail=str(exc))
        sample_data = _sample_to_dict(sample)

    return {
        "run_id": str(run_id),
        "model_target_id": str(target.id),
        "product_name": target.product_name,
        "question_id": str(question.id),
        "question_text": question.question_text,
        "answer_text": answer.answer_text,
        "page_url": answer.page_url,
        "screenshot_url": answer.screenshot_url,
        "sources": answer_sources,
        "source_count": len(answer_sources),
        "session": answer.session,
        "status_warning": answer.status_warning,
        "bridge_provider": answer.bridge_provider,
        "inferred_metrics": inferred,
        "sample": sample_data,
        "note": "自动判断结果仅作初筛，建议人工复核品牌提及、推荐和引用线索。",
    }


@router.post("/runs/{run_id}/calculate")
async def calculate_metrics(
    run_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """计算检测指标"""
    service = MonitoringService(db)
    result = await service.calculate_run_metrics(run_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/runs/{run_id}/compare/{baseline_run_id}")
async def compare_with_baseline(
    run_id: UUID,
    baseline_run_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """对比基线"""
    service = MonitoringService(db)
    result = await service.compare_with_baseline(run_id, baseline_run_id)
    return result


@router.post("/runs/{run_id}/recommendations")
async def generate_recommendations(
    run_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """基于检测结果生成下一轮优化建议，并写入 recommendations 表。"""
    service = MonitoringService(db)
    result = await service.generate_recommendations_for_run(run_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
