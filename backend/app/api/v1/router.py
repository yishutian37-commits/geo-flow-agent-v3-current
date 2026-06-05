from fastapi import APIRouter

from app.api.v1.endpoints import projects, brands, brand_facts, corpus_items, source_assets, channel_accounts, publish_records, questions, monitoring, reports, ai_models, dashboard, content_tasks, content_drafts, writing_memory, approvals, model_targets, baseline_runs, sentiments, auth, users, platform_policies, question_archetypes

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(brands.router, prefix="/brands", tags=["Brands"])
api_router.include_router(brand_facts.router, prefix="/brand-facts", tags=["Brand Facts"])
api_router.include_router(corpus_items.router, prefix="/corpus-items", tags=["Corpus Items"])
api_router.include_router(source_assets.router, prefix="/source-assets", tags=["Source Assets"])
api_router.include_router(channel_accounts.router, prefix="/channel-accounts", tags=["Channel Accounts"])
api_router.include_router(publish_records.router, prefix="/publish-records", tags=["Publish Records"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
api_router.include_router(content_tasks.router, prefix="/content-tasks", tags=["Content Tasks"])
api_router.include_router(content_drafts.router, prefix="/content-drafts", tags=["Content Drafts"])
api_router.include_router(writing_memory.router, prefix="/writing-memory", tags=["Writing Memory"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(model_targets.router, prefix="/model-targets", tags=["Model Targets"])
api_router.include_router(baseline_runs.router, prefix="/baseline-runs", tags=["Baseline Runs"])
api_router.include_router(sentiments.router, prefix="/sentiments", tags=["Sentiments"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(ai_models.router, prefix="/ai-models", tags=["AI Models"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(platform_policies.router, prefix="/platform-policies", tags=["Platform Policies"])
api_router.include_router(question_archetypes.router, prefix="/question-archetypes", tags=["Question Archetypes"])
