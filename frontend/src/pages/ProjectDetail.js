import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  Card, Descriptions, Tag, Tabs, Button, Progress, Alert, Spin, message, Modal, Form, Input, List, Space, Badge, Empty, Typography, Row, Col, Statistic, Select,
} from 'antd';
import {
  projectsApi, brandsApi, brandFactsApi, questionsApi, contentTasksApi, monitoringApi,
  approvalsApi, sourceAssetsApi, corpusItemsApi,
} from '../services/api';
import Table from '../components/SafeTable';

const { TabPane } = Tabs;
const { TextArea } = Input;
const { Text } = Typography;

const statusColors = {
  draft: 'default',
  confirmed: 'success',
  expired: 'error',
  disputed: 'warning',
  restricted: 'purple',
  active: 'processing',
  in_progress: 'processing',
  review: 'warning',
  approved: 'success',
  publish_ready: 'cyan',
  published: 'green',
  completed: 'success',
  blocked: 'error',
  running: 'processing',
};

const statusLabels = {
  draft: '草稿',
  confirmed: '已确认',
  expired: '已过期',
  disputed: '争议中',
  restricted: '受限',
  active: '进行中',
  in_progress: '进行中',
  review: '待审核',
  approved: '已通过',
  client_review: '客户复核',
  publish_ready: '待发布',
  published: '已发布',
  completed: '已完成',
  blocked: '已阻塞',
  running: '运行中',
};

const layerLabels = {
  exposure: '曝光/推荐层',
  verification: '验证/口碑层',
  conversion: '转化/承接层',
  verification_layer: '基础验证层',
  pool_layer: '入池层',
  weight_layer: '权重提升层',
  conversion_layer: '转化承接层',
};

const layerColors = {
  exposure: 'blue',
  verification: 'orange',
  conversion: 'purple',
  pool_layer: 'blue',
  verification_layer: 'orange',
  weight_layer: 'green',
  conversion_layer: 'purple',
};

const runTypeLabels = {
  web_auto: '网页自动检测',
  api: 'API检测',
  manual: '人工录入',
  baseline: '基线检测',
  post: '复测',
};

const samplePolicyLabels = {
  mvp: 'MVP抽样',
  full: '全量检测',
  key: '重点跟踪',
  monthly: '月度监测',
  acceptance: '验收样本',
  custom: '自定义',
};

const questionTypeLabels = {
  category: '品类问题',
  brand_reputation: '品牌声誉',
  comparison: '对比推荐',
  qualification: '资质验证',
  conversion: '转化咨询',
  after_sales: '售后/复训',
};

const keywordLayerLabels = {
  category: '品类词',
  region: '地域词',
  scenario: '场景/人群',
  proof: '证据验证',
  conversion: '转化承接',
  brand: '品牌主体',
  comparison: '对比竞品',
  other: '其他',
};

const searchAssetTypeLabels = {
  official_site: '官网/官方页',
  qualification: '资质证明',
  case_page: '案例页',
  media_report: '媒体报道',
  faq: '问答/FAQ',
  comparison: '对比测评',
  local_guide: '本地指南',
  contact_page: '联系/承接页',
  product_page: '产品/服务页',
  other: '其他',
};

const parseTags = (value) => String(value || '')
  .split(/[,，、\s]+/)
  .map((item) => item.trim())
  .filter(Boolean);

const getDetectionMode = (record) => {
  const sampleCount = Number(record?.sample_count || 0);
  if (sampleCount > 1) return { label: '批量检测', color: 'blue' };
  if (sampleCount === 1) return { label: '单题检测', color: 'gold' };
  return { label: '未采样', color: 'default' };
};

const shortId = (value) => (value ? String(value).slice(0, 8) : '');

function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [projectBrands, setProjectBrands] = useState([]);

  // 事实库
  const [facts, setFacts] = useState([]);
  const [factsLoading, setFactsLoading] = useState(false);
  const [addFactVisible, setAddFactVisible] = useState(false);
  const [extractFactsVisible, setExtractFactsVisible] = useState(false);
  const [extractingFacts, setExtractingFacts] = useState(false);
  const [factForm] = Form.useForm();
  const [extractFactsForm] = Form.useForm();

  // 资料缺口诊断
  const [gapResult, setGapResult] = useState(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [diagnosingFromFacts, setDiagnosingFromFacts] = useState(false);
  const [diagnoseVisible, setDiagnoseVisible] = useState(false);
  const [diagnoseFields, setDiagnoseFields] = useState('');
  const [diagnosisReport, setDiagnosisReport] = useState(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);

  // 信源资产
  const [sourceAssets, setSourceAssets] = useState([]);
  const [sourceAssetsLoading, setSourceAssetsLoading] = useState(false);
  const [addSourceAssetVisible, setAddSourceAssetVisible] = useState(false);
  const [sourceAssetForm] = Form.useForm();

  // 项目知识资产
  const [knowledgeAssets, setKnowledgeAssets] = useState([]);
  const [knowledgeAssetsLoading, setKnowledgeAssetsLoading] = useState(false);

  // 问题库
  const [questionGroups, setQuestionGroups] = useState([]);
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [generatingQuestions, setGeneratingQuestions] = useState(false);
  const [questionGenerationStrategy, setQuestionGenerationStrategy] = useState(null);
  const [generatingContentTasks, setGeneratingContentTasks] = useState(false);
  const [addQuestionVisible, setAddQuestionVisible] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState(null);
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [questionForm] = Form.useForm();

  // 内容任务
  const [tasks, setTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [transitioningTaskId, setTransitioningTaskId] = useState(null);
  const [approvingKey, setApprovingKey] = useState(null);

  // 检测记录
  const [monitoringRuns, setMonitoringRuns] = useState([]);
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [generatingRecommendationsRunId, setGeneratingRecommendationsRunId] = useState(null);

  const loadProject = useCallback(async () => {
    setLoading(true);
    try {
      const [projectRes, brandsRes] = await Promise.all([
        projectsApi.get(id),
        projectsApi.getBrands(id),
      ]);
      setProject(projectRes.data);
      setProjectBrands(brandsRes.data || []);
    } catch (error) {
      message.error('加载项目失败');
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadFacts = useCallback(async () => {
    setFactsLoading(true);
    try {
      // 通过 project_id 筛选，只显示当前项目下所有品牌的事实
      const res = await brandFactsApi.list({ project_id: id, limit: 100 });
      setFacts(res.data || []);
    } catch (error) {
      message.error('加载品牌事实失败');
    } finally {
      setFactsLoading(false);
    }
  }, [id]);

  const loadQuestions = useCallback(async () => {
    setQuestionsLoading(true);
    try {
      const res = await questionsApi.listGroups({ project_id: id });
      setQuestionGroups(res.data || []);
    } catch (error) {
      message.error('加载问题库失败');
    } finally {
      setQuestionsLoading(false);
    }
  }, [id]);

  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const res = await contentTasksApi.list({ project_id: id });
      setTasks(res.data || []);
    } catch (error) {
      message.error('加载内容任务失败');
    } finally {
      setTasksLoading(false);
    }
  }, [id]);

  const loadMonitoring = useCallback(async () => {
    setMonitoringLoading(true);
    try {
      const res = await monitoringApi.listRuns({ project_id: id });
      setMonitoringRuns(res.data || []);
    } catch (error) {
      message.error('加载检测记录失败');
    } finally {
      setMonitoringLoading(false);
    }
  }, [id]);

  const loadSourceAssets = useCallback(async () => {
    setSourceAssetsLoading(true);
    try {
      const res = await sourceAssetsApi.list({ project_id: id, limit: 100 });
      setSourceAssets(res.data || []);
    } catch (error) {
      message.error('加载信源资产失败');
    } finally {
      setSourceAssetsLoading(false);
    }
  }, [id]);

  const loadKnowledgeAssets = useCallback(async () => {
    setKnowledgeAssetsLoading(true);
    try {
      const res = await corpusItemsApi.list({ project_id: id, limit: 1000 });
      setKnowledgeAssets(res.data || []);
    } catch (error) {
      message.error('加载项目知识资产失败');
    } finally {
      setKnowledgeAssetsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadProject();
    loadFacts();
    loadQuestions();
    loadTasks();
    loadMonitoring();
    loadSourceAssets();
    loadKnowledgeAssets();
  }, [loadProject, loadFacts, loadQuestions, loadTasks, loadMonitoring, loadSourceAssets, loadKnowledgeAssets]);

  const knowledgeLoopStats = useMemo(() => {
    const questionCount = questionGroups.reduce((sum, group) => sum + (group.questions?.length || 0), 0);
    const sampleCount = monitoringRuns.reduce((sum, run) => sum + Number(run.sample_count || 0), 0);
    const reviewCount = knowledgeAssets.filter((item) => item.knowledge_layer === 'review_data').length;
    return {
      knowledgeCount: knowledgeAssets.length,
      confirmedFactCount: facts.filter((item) => item.status === 'confirmed').length,
      questionCount,
      taskCount: tasks.length,
      sampleCount,
      reviewCount,
    };
  }, [facts, knowledgeAssets, monitoringRuns, questionGroups, tasks]);

  const handleDiagnose = async () => {
    setGapLoading(true);
    try {
      const fields = diagnoseFields.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean);
      const res = await projectsApi.diagnoseGaps(id, fields.length > 0 ? fields : []);
      setGapResult(res.data);
      message.success('资料缺口诊断完成');
      setDiagnoseVisible(false);
    } catch (error) {
      message.error('诊断失败');
    } finally {
      setGapLoading(false);
    }
  };

  const handleDiagnoseFromFacts = async () => {
    setDiagnosingFromFacts(true);
    setGapLoading(true);
    try {
      const res = await projectsApi.diagnoseGapsFromFacts(id);
      setGapResult(res.data);
      message.success(`已按事实库完成诊断：确认字段 ${res.data?.provided_fields?.length || 0} 个，待处理动作 ${res.data?.action_items?.length || 0} 个`);
    } catch (error) {
      message.error('事实库诊断失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setDiagnosingFromFacts(false);
      setGapLoading(false);
    }
  };

  const handleGenerateQuestions = async () => {
    setGeneratingQuestions(true);
    try {
      const brandName = projectBrands[0]?.brand_name || project?.name || '该品牌';
      const res = await projectsApi.generateQuestionBank(id, brandName);
      const sourceText = res.data?.source === 'llm' ? 'AI生成' : '本地矩阵模板';
      setQuestionGenerationStrategy(res.data?.generation_strategy || null);
      message.success(`问题库已生成：${res.data?.generated_groups || 0}组 / ${res.data?.generated_questions || 0}条（${sourceText}）`);
      loadQuestions();
    } catch (error) {
      message.error('生成失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGeneratingQuestions(false);
    }
  };

  const handleLoadDiagnosisReport = async () => {
    setDiagnosisLoading(true);
    try {
      const res = await projectsApi.getDiagnosisReport(id);
      setDiagnosisReport(res.data);
      message.success('AI 诊断报告已生成');
    } catch (error) {
      message.error('生成诊断报告失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setDiagnosisLoading(false);
    }
  };

  const handleGenerateContentTasks = async () => {
    setGeneratingContentTasks(true);
    try {
      const res = await projectsApi.generateContentMatrix(id, { replace_existing: false });
      message.success(`已从问题矩阵生成内容任务：新增 ${res.data?.created_tasks || 0} 个，跳过 ${res.data?.skipped_tasks || 0} 个`);
      loadTasks();
    } catch (error) {
      message.error('生成内容任务失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGeneratingContentTasks(false);
    }
  };

  const handleAddFact = async (values) => {
    let brandId = projectBrands[0]?.id;
    try {
      if (!brandId) {
        const brandRes = await brandsApi.create({
          project_id: id,
          brand_name: project?.name || 'Default Brand',
          company_name: project?.name || '',
          description: project?.notes || '',
        });
        const createdBrand = brandRes.data;
        brandId = createdBrand.id;
        setProjectBrands([createdBrand]);
        message.info('已自动创建品牌主体');
      }
      await brandFactsApi.create({ ...values, brand_id: brandId });
      message.success('品牌事实已添加');
      setAddFactVisible(false);
      factForm.resetFields();
      loadFacts();
    } catch (error) {
      message.error('添加失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const ensureProjectBrand = async () => {
    const existingBrand = projectBrands[0];
    if (existingBrand?.id) return existingBrand;

    const brandRes = await brandsApi.create({
      project_id: id,
      brand_name: project?.name || 'Default Brand',
      company_name: project?.name || '',
      description: project?.notes || '',
    });
    const createdBrand = brandRes.data;
    setProjectBrands([createdBrand]);
    return createdBrand;
  };

  const handleExtractFactsFromText = async (values) => {
    setExtractingFacts(true);
    try {
      const brand = await ensureProjectBrand();
      const res = await brandFactsApi.extractFromText({
        brand_id: brand.id,
        content: values.content,
        source: values.source || '企业资料粘贴文本',
        max_facts: Number(values.max_facts || 24),
      });
      const count = Array.isArray(res.data) ? res.data.length : 0;
      message.success(`已提取 ${count} 条品牌事实候选，请逐条确认`);
      setExtractFactsVisible(false);
      extractFactsForm.resetFields();
      loadFacts();
    } catch (error) {
      message.error('AI 提取失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setExtractingFacts(false);
    }
  };

  const handleAddSourceAsset = async (values) => {
    try {
      await sourceAssetsApi.create({
        project_id: id,
        ...values,
      });
      message.success('信源资产已添加');
      setAddSourceAssetVisible(false);
      sourceAssetForm.resetFields();
      loadSourceAssets();
    } catch (error) {
      message.error('添加信源资产失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDeleteSourceAsset = async (asset) => {
    Modal.confirm({
      title: '删除信源资产',
      content: `确认删除 ${asset.platform || asset.source_type || asset.url || '该信源'} 吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await sourceAssetsApi.delete(asset.id);
        message.success('信源资产已删除');
        loadSourceAssets();
      },
    });
  };

  const handleConfirmFact = async (factId) => {
    try {
      await brandFactsApi.confirm(factId);
      message.success('事实已确认');
      loadFacts();
    } catch (error) {
      message.error('确认失败');
    }
  };

  const handleSaveQuestion = async (values) => {
    if (!selectedGroupId && !editingQuestion?.group_id) return;
    const payload = {
      ...values,
      priority: Number(values.priority || 50),
      enabled: values.enabled !== false,
      focus: values.focus === true,
    };
    try {
      if (editingQuestion?.id) {
        await questionsApi.updateQuestion(editingQuestion.id, payload);
        message.success('问题已更新');
      } else {
        await questionsApi.createQuestion(selectedGroupId, payload);
        message.success('问题已添加');
      }
      setAddQuestionVisible(false);
      setEditingQuestion(null);
      questionForm.resetFields();
      loadQuestions();
    } catch (error) {
      message.error('保存失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleToggleQuestion = async (question, field) => {
    try {
      await questionsApi.updateQuestion(question.id, { [field]: !question[field] });
      message.success(field === 'enabled' ? '启用状态已更新' : '重点关注已更新');
      loadQuestions();
    } catch (error) {
      message.error('更新失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDeleteQuestion = (question) => {
    Modal.confirm({
      title: '删除问题',
      content: `确认删除“${question.question_text}”吗？该问题的历史检测样本仍会保留，但后续不能再选它发起新检测。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await questionsApi.deleteQuestion(question.id);
        message.success('问题已删除');
        loadQuestions();
      },
    });
  };

  const nextTaskStatus = (status) => ({
    draft: 'in_progress',
    in_progress: 'review',
    rework: 'in_progress',
    review: 'approved',
    approved: 'client_review',
    client_review: 'publish_ready',
    publish_ready: 'published',
  }[status]);

  const handleAdvanceTask = async (task) => {
    const targetStatus = nextTaskStatus(task.status);
    if (!targetStatus) return;
    setTransitioningTaskId(task.id);
    try {
      await contentTasksApi.transition(task.id, { target_status: targetStatus });
      message.success(`任务状态已更新为 ${statusLabels[targetStatus] || targetStatus}`);
      loadTasks();
    } catch (error) {
      message.error('状态流转失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setTransitioningTaskId(null);
    }
  };

  const handleApproveTaskStep = async (task, step, label) => {
    const key = `${task.id}-${step}`;
    setApprovingKey(key);
    try {
      const res = await approvalsApi.list({ object_type: 'content_task', object_id: task.id });
      let approval = (res.data || []).find((item) => item.step === step);
      if (!approval) {
        const created = await approvalsApi.create({
          object_type: 'content_task',
          object_id: task.id,
          step,
          comment: `${label}手动补建审批记录`,
        });
        approval = created.data;
      }
      await approvalsApi.decide(approval.id, {
        decision: 'approved',
        comment: `${label}已通过`,
      });
      message.success(`${label}已通过`);
    } catch (error) {
      message.error(`${label}失败: ` + (error.response?.data?.detail || error.message));
    } finally {
      setApprovingKey(null);
    }
  };

  const handleGenerateRecommendations = async (run) => {
    setGeneratingRecommendationsRunId(run.id);
    try {
      const res = await monitoringApi.generateRecommendations(run.id);
      const recommendations = res.data?.recommendations || [];
      Modal.info({
        title: '下一轮优化建议',
        width: 720,
        content: (
          <List
            size="small"
            dataSource={recommendations}
            locale={{ emptyText: '本轮检测未发现需要新增的优化建议' }}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={2}>
                  <Space>
                    <Tag color={item.priority === 'high' ? 'red' : 'orange'}>{item.priority}</Tag>
                    <Text strong>{item.recommendation_type}</Text>
                  </Space>
                  <Text>{item.reason}</Text>
                  {item.linked_metric && <Text type="secondary">关联指标：{item.linked_metric}</Text>}
                </Space>
              </List.Item>
            )}
          />
        ),
      });
    } catch (error) {
      message.error('生成优化建议失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGeneratingRecommendationsRunId(null);
    }
  };

  const handleDeleteMonitoringRun = (run) => {
    const mode = getDetectionMode(run);
    Modal.confirm({
      title: '删除检测记录',
      content: `确认删除这条${mode.label || '检测记录'}吗？删除后会同时清理该记录下的回答样本、情绪记录和截图证据文件。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await monitoringApi.deleteRun(run.id);
          message.success('检测记录已删除');
          await loadMonitoring();
        } catch (error) {
          message.error('删除检测记录失败: ' + (error.response?.data?.detail || error.message));
          throw error;
        }
      },
    });
  };

  const openAddQuestion = (groupId) => {
    setSelectedGroupId(groupId);
    setEditingQuestion(null);
    questionForm.resetFields();
    questionForm.setFieldsValue({
      question_type: 'brand_reputation',
      keyword_breakdown: '',
      keyword_layer: 'category',
      question_formula: '',
      knowledge_need: '',
      search_asset_type: 'faq',
      business_value: 'medium',
      evidence_support: '',
      content_actionability: '',
      recommended_platforms: '',
      priority: 50,
      sample_policy: 'mvp',
      enabled: true,
      focus: false,
    });
    setAddQuestionVisible(true);
  };

  const openEditQuestion = (groupId, question) => {
    setSelectedGroupId(groupId);
    setEditingQuestion(question);
    questionForm.setFieldsValue({
      question_text: question.question_text,
      question_type: question.question_type || 'brand_reputation',
      tags: question.tags || '',
      keyword_breakdown: question.keyword_breakdown || '',
      keyword_layer: question.keyword_layer || 'category',
      question_formula: question.question_formula || '',
      knowledge_need: question.knowledge_need || '',
      search_asset_type: question.search_asset_type || 'faq',
      business_value: question.business_value || 'medium',
      evidence_support: question.evidence_support || '',
      content_actionability: question.content_actionability || '',
      recommended_platforms: question.recommended_platforms || '',
      priority: question.priority || 50,
      sample_policy: question.sample_policy || 'mvp',
      enabled: question.enabled !== false,
      focus: question.focus === true,
    });
    setAddQuestionVisible(true);
  };

  if (loading) return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  if (!project) return <div>项目不存在</div>;

  const brandFactColumns = [
    {
      title: '事实类型',
      dataIndex: 'fact_type',
      key: 'fact_type',
      render: (t) => {
        const labels = { qualification: '资质', address: '地址', phone: '电话', price: '价格', case_study: '案例', contact: '联系方式', founding_date: '成立时间', product: '产品', service: '服务', certification: '证书' };
        return labels[t] || t;
      },
    },
    { title: '值', dataIndex: 'value', key: 'value', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>,
    },
    {
      title: '公开范围',
      dataIndex: 'fact_scope',
      key: 'fact_scope',
      render: (s) => <Tag color={s === 'public' ? 'blue' : s === 'internal' ? 'orange' : 'red'}>{s === 'public' ? '公开' : s === 'internal' ? '内部' : '受限'}</Tag>,
    },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (r) => <Tag color={r === 'high' ? 'red' : r === 'medium' ? 'orange' : 'green'}>{r === 'high' ? '高' : r === 'medium' ? '中' : '低'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button type="link" disabled={record.status === 'confirmed'} onClick={() => handleConfirmFact(record.id)}>
          {record.status === 'confirmed' ? '已确认' : '确认'}
        </Button>
      ),
    },
  ];

  const taskColumns = [
    { title: '内容类型', dataIndex: 'content_type', key: 'content_type' },
    {
      title: '层级',
      dataIndex: 'layer',
      key: 'layer',
      render: (l) => <Tag color={l === 'verification_layer' ? 'blue' : l === 'pool_layer' ? 'green' : l === 'weight_layer' ? 'orange' : 'purple'}>{layerLabels[l] || l}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (p) => <Badge color={p === 'high' ? 'red' : p === 'medium' ? 'orange' : 'blue'} text={p === 'high' ? '高' : p === 'medium' ? '中' : '低'} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>,
    },
    { title: '截止日期', dataIndex: 'due_date', key: 'due_date', render: (d) => d ? new Date(d).toLocaleDateString() : '-' },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => {
        const targetStatus = nextTaskStatus(record.status);
        const reviewActions = record.status === 'review' ? (
          <>
            <Button size="small" loading={approvingKey === `${record.id}-compliance_review`} onClick={() => handleApproveTaskStep(record, 'compliance_review', '合规审核')}>
              合规通过
            </Button>
            <Button size="small" loading={approvingKey === `${record.id}-project_owner_review`} onClick={() => handleApproveTaskStep(record, 'project_owner_review', '终审')}>
              终审通过
            </Button>
          </>
        ) : null;
        const clientAction = record.status === 'client_review' ? (
          <Button size="small" loading={approvingKey === `${record.id}-client_review`} onClick={() => handleApproveTaskStep(record, 'client_review', '客户复核')}>
            客户通过
          </Button>
        ) : null;
        return (
          <Space wrap>
            {reviewActions}
            {clientAction}
            {targetStatus ? (
              <Button size="small" loading={transitioningTaskId === record.id} onClick={() => handleAdvanceTask(record)}>
                推进到{statusLabels[targetStatus] || targetStatus}
              </Button>
            ) : <Text type="secondary">-</Text>}
          </Space>
        );
      },
    },
  ];

  const monitoringColumns = [
    {
      title: '检测方式',
      key: 'detection_mode',
      width: 180,
      render: (_, record) => {
        const mode = getDetectionMode(record);
        return (
          <Space direction="vertical" size={2}>
            <Tag color={mode.color}>{mode.label}</Tag>
            <Text type="secondary">{runTypeLabels[record.run_type] || record.run_type || '-'}</Text>
          </Space>
        );
      },
    },
    {
      title: '检测平台',
      key: 'model_target',
      width: 240,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text strong>{record.model_target_name || '未绑定平台'}</Text>
          <Text type="secondary">
            {record.model_target_id ? `平台ID：${shortId(record.model_target_id)}` : '未记录平台ID'}
          </Text>
        </Space>
      ),
    },
    {
      title: '样本数',
      dataIndex: 'sample_count',
      key: 'sample_count',
      width: 100,
      render: (value) => `${value || 0} 个`,
    },
    {
      title: '机制',
      dataIndex: 'mechanism_type',
      key: 'mechanism_type',
      width: 90,
      render: (m) => <Tag>{m}</Tag>,
    },
    {
      title: '采样策略',
      dataIndex: 'sample_policy',
      key: 'sample_policy',
      width: 120,
      render: (s) => <Tag color="blue">{samplePolicyLabels[s] || s}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s) => <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>,
    },
    { title: '开始时间', dataIndex: 'started_at', key: 'started_at', width: 190, render: (d) => d ? new Date(d).toLocaleString() : '-' },
    {
      title: '操作',
      key: 'action',
      width: 190,
      render: (_, record) => (
        <Space wrap>
          <Button size="small" loading={generatingRecommendationsRunId === record.id} onClick={() => handleGenerateRecommendations(record)}>
            生成建议
          </Button>
          <Button size="small" danger onClick={() => handleDeleteMonitoringRun(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const sourceAssetColumns = [
    {
      title: '信源类型',
      dataIndex: 'source_type',
      key: 'source_type',
      render: (value) => {
        const labels = {
          official_site: '官网',
          qualification: '资质公示',
          case_page: '案例页',
          media_report: '媒体报道',
          knowledge_base: '百科/知识库',
          social_account: '官方账号',
        };
        return labels[value] || value;
      },
    },
    { title: '平台/来源', dataIndex: 'platform', key: 'platform', render: (value) => value || '-' },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (value) => value ? <a href={value} target="_blank" rel="noreferrer">{value}</a> : '-',
    },
    {
      title: '权威度',
      dataIndex: 'authority_level',
      key: 'authority_level',
      render: (value) => <Tag color={value === 'high' ? 'green' : value === 'low' ? 'orange' : 'blue'}>{value}</Tag>,
    },
    {
      title: '可抓取性',
      dataIndex: 'crawlability',
      key: 'crawlability',
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value) => <Tag color={value === 'active' ? 'green' : 'default'}>{value}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button type="link" danger onClick={() => handleDeleteSourceAsset(record)}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h2>{project.name}</h2>
      <Card style={{ marginBottom: 16 }}>
        <Descriptions bordered>
          <Descriptions.Item label="行业">{project.industry}</Descriptions.Item>
          <Descriptions.Item label="地区">{project.region}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={project.status === 'active' ? 'green' : 'default'}>{project.status === 'active' ? '进行中' : project.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="预算">{project.budget ? `¥${project.budget.toLocaleString()}` : '-'}</Descriptions.Item>
          <Descriptions.Item label="检测平台">{project.target_ai_products || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{new Date(project.created_at).toLocaleString()}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="GEO 知识闭环"
        style={{ marginBottom: 16 }}
        extra={<Button size="small" loading={knowledgeAssetsLoading} onClick={loadKnowledgeAssets}>刷新知识资产</Button>}
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="知识资产" value={knowledgeLoopStats.knowledgeCount} suffix="条" />
          </Col>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="已确认事实" value={knowledgeLoopStats.confirmedFactCount} suffix="条" />
          </Col>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="问题覆盖" value={knowledgeLoopStats.questionCount} suffix="条" />
          </Col>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="内容任务" value={knowledgeLoopStats.taskCount} suffix="个" />
          </Col>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="检测样本" value={knowledgeLoopStats.sampleCount} suffix="条" />
          </Col>
          <Col xs={12} md={8} lg={4}>
            <Statistic title="复盘资料" value={knowledgeLoopStats.reviewCount} suffix="条" />
          </Col>
        </Row>
        <Alert
          style={{ marginTop: 16 }}
          type="info"
          showIcon
          message="闭环链路"
          description={(
            <Space wrap>
              {['资料', '事实', '问题', '内容', '发布', '复测', '复盘资料'].map((item, index) => (
                <React.Fragment key={item}>
                  <Tag color={index === 6 ? 'purple' : 'blue'}>{item}</Tag>
                  {index < 6 && <Text type="secondary">→</Text>}
                </React.Fragment>
              ))}
              <Text type="secondary">复盘资料会回到项目知识库，后续可继续参与问题矩阵和内容生成。</Text>
            </Space>
          )}
        />
      </Card>

      <Tabs defaultActiveKey="1">
        <TabPane tab="品牌事实库" key="1">
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" onClick={() => setExtractFactsVisible(true)}>AI 批量提取企业资料</Button>
            <Button onClick={() => setAddFactVisible(true)}>手动添加事实</Button>
          </Space>
          <Spin spinning={factsLoading}>
            <Table columns={brandFactColumns} dataSource={facts} rowKey="id" locale={{ emptyText: '暂无品牌事实，请添加' }} />
          </Spin>
        </TabPane>

        <TabPane tab="资料缺口诊断" key="2">
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" loading={diagnosingFromFacts} onClick={handleDiagnoseFromFacts}>按事实库自动诊断</Button>
            <Button onClick={() => setDiagnoseVisible(true)}>手动字段诊断</Button>
          </Space>
          {gapResult && (
            <div>
              <Alert
                message="资料完整性"
                description={<div><Progress percent={Math.round(gapResult.completeness_score || 0)} status="active" /><p>完整度: {(gapResult.completeness_score || 0).toFixed(1)}%</p></div>}
                type="info"
                showIcon
              />
              {gapResult.missing_required?.length > 0 && (
                <Card title="缺失必填项" style={{ marginTop: 16 }}>
                  <List dataSource={gapResult.missing_required} renderItem={(item) => <List.Item><Tag color="red">必填</Tag> {item.label || item.field || item}</List.Item>} />
                </Card>
              )}
              {gapResult.missing_optional?.length > 0 && (
                <Card title="缺失可选项" style={{ marginTop: 16 }}>
                  <List dataSource={gapResult.missing_optional} renderItem={(item) => <List.Item><Tag color="orange">可选</Tag> {item.label || item.field || item}</List.Item>} />
                </Card>
              )}
              {gapResult.pending_fields?.length > 0 && (
                <Card title="已有候选但未确认" style={{ marginTop: 16 }}>
                  <List dataSource={gapResult.pending_fields} renderItem={(item) => <List.Item><Tag color="gold">待确认</Tag> {item.label || item.field || item}</List.Item>} />
                </Card>
              )}
              {gapResult.action_items?.length > 0 && (
                <Card title="补齐动作" style={{ marginTop: 16 }}>
                  <List dataSource={gapResult.action_items} renderItem={(item) => (
                    <List.Item>
                      <Space direction="vertical" size={2}>
                        <Space>
                          <Tag color={item.priority === 'high' ? 'red' : 'orange'}>{item.label || item.field}</Tag>
                          <Text>{item.action_type}</Text>
                        </Space>
                        <Text type="secondary">{item.suggestion}</Text>
                      </Space>
                    </List.Item>
                  )}
                  />
                </Card>
              )}
            </div>
          )}
          {!gapResult && !gapLoading && <Alert message="尚未进行资料缺口诊断" description="建议优先按事实库自动诊断；如需校准，也可以手动输入已收集字段。" type="info" showIcon />}
          <Spin spinning={gapLoading} />
        </TabPane>

        <TabPane tab="AI品牌体检" key="6">
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" loading={diagnosisLoading} onClick={handleLoadDiagnosisReport}>
              生成诊断报告
            </Button>
          </Space>
          <Spin spinning={diagnosisLoading}>
            {!diagnosisReport ? (
              <Alert
                message="尚未生成 AI 品牌体检"
                description="该诊断会基于已录入的检测样本，归纳品牌提及、推荐、回答维度、竞品线索和下一步动作。"
                type="info"
                showIcon
              />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={16}>
                  <Col span={6}><Card><Statistic title="样本数" value={diagnosisReport.sample_count || 0} /></Card></Col>
                  <Col span={6}><Card><Statistic title="提及率" value={diagnosisReport.brand_health?.mention_rate || 0} suffix="%" /></Card></Col>
                  <Col span={6}><Card><Statistic title="推荐率" value={diagnosisReport.brand_health?.recommendation_rate || 0} suffix="%" /></Card></Col>
                  <Col span={6}><Card><Statistic title="公开事实" value={diagnosisReport.brand_health?.public_confirmed_facts || 0} /></Card></Col>
                </Row>
                <Alert
                  message={diagnosisReport.brand_health?.known_state || '暂无判断'}
                  description="该结论为样本观察，不代表模型内部排序逻辑。"
                  type="success"
                  showIcon
                />
                <Card title="回答模式维度">
                  <List
                    dataSource={diagnosisReport.answer_pattern?.dimension_counts || []}
                    renderItem={(item) => (
                      <List.Item>
                        <Space>
                          <Tag color={item.sample_hits > 0 ? 'blue' : 'default'}>{item.dimension}</Tag>
                          <Text>{item.sample_hits} 个样本命中</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
                <Card title="问题层级表现">
                  <List
                    dataSource={diagnosisReport.answer_pattern?.layer_summary || []}
                    renderItem={(item) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Space>
                            <Tag color={layerColors[item.layer] || 'default'}>{item.layer_label}</Tag>
                            <Text>样本 {item.sample_count}，提及率 {item.mention_rate}%，推荐率 {item.recommendation_rate}%</Text>
                          </Space>
                          <Text type="secondary">机制：{(item.mechanisms || []).join(', ') || '-'}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
                <Card title="竞品差距线索">
                  <List
                    dataSource={diagnosisReport.competitor_gap?.detected_competitors || []}
                    locale={{ emptyText: '暂无可识别竞品线索，建议后续补充竞品名单或增加样本' }}
                    renderItem={(item) => <List.Item><Tag>{item.name}</Tag> 出现 {item.mention_count} 次</List.Item>}
                  />
                  <Text type="secondary">{diagnosisReport.competitor_gap?.note}</Text>
                </Card>
                <Card title="下一步动作">
                  <List
                    dataSource={diagnosisReport.actions || []}
                    renderItem={(item) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Space><Tag color={item.priority === 'high' ? 'red' : 'orange'}>{item.priority}</Tag><Text strong>{item.action}</Text></Space>
                          <Text type="secondary">{item.reason}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
              </Space>
            )}
          </Spin>
        </TabPane>

        <TabPane tab={<span>信源资产 <Badge count={sourceAssets.length} showZero style={{ backgroundColor: '#13c2c2' }} /></span>} key="7">
          <Alert
            message="信源资产用于记录官网、资质公示、案例页、媒体报道等可被生成式引擎引用的公开资料。检测时请把回答中的显式引用和来源匹配录入样本，系统会计算引用率。"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" onClick={() => setAddSourceAssetVisible(true)}>添加信源资产</Button>
            <Button onClick={loadSourceAssets}>刷新</Button>
          </Space>
          <Spin spinning={sourceAssetsLoading}>
            <Table columns={sourceAssetColumns} dataSource={sourceAssets} rowKey="id" locale={{ emptyText: '暂无信源资产，请先添加官网、资质页、案例页或媒体报道' }} />
          </Spin>
        </TabPane>

        <TabPane tab={<span>问题库 <Badge count={questionGroups.length} showZero style={{ backgroundColor: '#52c41a' }} /></span>} key="3">
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" loading={generatingQuestions} onClick={handleGenerateQuestions}>
              生成问题库
            </Button>
            <Button loading={generatingContentTasks} disabled={questionGroups.length === 0} onClick={handleGenerateContentTasks}>
              生成内容任务
            </Button>
          </Space>
          {questionGenerationStrategy && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="本轮问题生成依据"
              description={(
                <Space direction="vertical" size={6}>
                  <Text>
                    {questionGenerationStrategy.principle}
                  </Text>
                  <Text type="secondary">
                    关键词：
                    {Object.entries(questionGenerationStrategy.keyword_breakdown || {})
                      .filter(([key]) => key !== 'fact_source_preview')
                      .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.slice(0, 8).join('、') : value}`)
                      .join('；')}
                  </Text>
                  <Text type="secondary">
                    问题公式：
                    {(questionGenerationStrategy.question_formulas || [])
                      .map((item) => `${item.name}=${item.formula}`)
                      .join('；')}
                  </Text>
                </Space>
              )}
            />
          )}
          <Spin spinning={questionsLoading}>
            {questionGroups.length === 0 ? (
              <Empty description="暂无问题库，点击上方按钮生成 GEO 问题矩阵" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {questionGroups.map((group) => (
                  <Card
                    key={group.id}
                    size="small"
                    title={
                      <Space>
                        <Tag color={layerColors[group.layer] || 'default'}>
                          {layerLabels[group.layer] || group.layer}
                        </Tag>
                        <Text strong>{group.intent_name}</Text>
                      </Space>
                    }
                    extra={<Button type="link" size="small" onClick={() => openAddQuestion(group.id)}>添加问题</Button>}
                  >
                    <Text type="secondary">代表性问题: {group.representative_question}</Text>
                    <List
                      size="small"
                      dataSource={group.questions || []}
                      renderItem={(q) => (
                        <List.Item
                          actions={[
                            <Button key="focus" type="link" size="small" onClick={() => handleToggleQuestion(q, 'focus')}>
                              {q.focus ? '取消重点' : '设为重点'}
                            </Button>,
                            <Button key="enabled" type="link" size="small" onClick={() => handleToggleQuestion(q, 'enabled')}>
                              {q.enabled === false ? '启用' : '停用'}
                            </Button>,
                            <Button key="edit" type="link" size="small" onClick={() => openEditQuestion(group.id, q)}>
                              编辑
                            </Button>,
                            <Button key="delete" type="link" size="small" danger onClick={() => handleDeleteQuestion(q)}>
                              删除
                            </Button>,
                          ]}
                        >
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            <Space wrap>
                              <Badge color={q.enabled === false ? 'gray' : q.focus ? 'red' : 'blue'} />
                              <Text delete={q.enabled === false}>{q.question_text}</Text>
                              {q.focus && <Tag color="red">重点关注</Tag>}
                              <Tag color={q.enabled === false ? 'default' : 'green'}>{q.enabled === false ? '已停用' : '启用中'}</Tag>
                              <Tag>{questionTypeLabels[q.question_type] || q.question_type || '品牌声誉'}</Tag>
                              <Tag>{samplePolicyLabels[q.sample_policy] || q.sample_policy}</Tag>
                              <Tag color="blue">P{q.priority || 50}</Tag>
                            </Space>
                            {parseTags(q.tags).length > 0 && (
                              <Space wrap size={4}>
                                {parseTags(q.tags).map((tag) => (
                                  <Tag key={`${q.id}-${tag}`} color="geekblue">{tag}</Tag>
                                ))}
                              </Space>
                            )}
                            {(q.keyword_layer || q.search_asset_type) && (
                              <Space wrap size={6}>
                                {q.keyword_layer && (
                                  <Tag color="gold">关键词层：{keywordLayerLabels[q.keyword_layer] || q.keyword_layer}</Tag>
                                )}
                                {q.search_asset_type && (
                                  <Tag color="lime">搜索资产：{searchAssetTypeLabels[q.search_asset_type] || q.search_asset_type}</Tag>
                                )}
                              </Space>
                            )}
                            {(q.question_formula || q.business_value || q.recommended_platforms) && (
                              <Space wrap size={6}>
                                {q.question_formula && <Tag color="purple">公式：{q.question_formula}</Tag>}
                                {q.business_value && <Tag color={q.business_value === 'high' ? 'red' : q.business_value === 'medium' ? 'orange' : 'default'}>商业价值：{q.business_value}</Tag>}
                                {parseTags(q.recommended_platforms).map((platform) => (
                                  <Tag key={`${q.id}-platform-${platform}`} color="cyan">{platform}</Tag>
                                ))}
                              </Space>
                            )}
                            {q.evidence_support && (
                              <Text type="secondary">证据支撑：{q.evidence_support}</Text>
                            )}
                            {q.knowledge_need && (
                              <Text type="secondary">知识需求：{q.knowledge_need}</Text>
                            )}
                            {q.content_actionability && (
                              <Text type="secondary">内容建议：{q.content_actionability}</Text>
                            )}
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Card>
                ))}
              </Space>
            )}
          </Spin>
        </TabPane>

        <TabPane tab={<span>内容任务 <Badge count={tasks.length} showZero style={{ backgroundColor: '#1890ff' }} /></span>} key="4">
          <Spin spinning={tasksLoading}>
            <Table columns={taskColumns} dataSource={tasks} rowKey="id" locale={{ emptyText: '暂无内容任务' }} />
          </Spin>
        </TabPane>

        <TabPane tab={<span>检测记录 <Badge count={monitoringRuns.length} showZero style={{ backgroundColor: '#722ed1' }} /></span>} key="5">
          <Spin spinning={monitoringLoading}>
            <Table columns={monitoringColumns} dataSource={monitoringRuns} rowKey="id" locale={{ emptyText: '暂无检测记录' }} />
          </Spin>
        </TabPane>
      </Tabs>

      {/* AI批量提取企业资料Modal */}
      <Modal
        title="AI 批量提取企业资料"
        open={extractFactsVisible}
        onOk={() => extractFactsForm.submit()}
        onCancel={() => setExtractFactsVisible(false)}
        confirmLoading={extractingFacts}
        okText="开始提取"
        width={820}
      >
        <Alert
          message="AI 只会创建待确认的事实候选。资质、证书编号、价格、通过率等信息仍需人工确认后，才会用于文章生成。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form
          form={extractFactsForm}
          layout="vertical"
          onFinish={handleExtractFactsFromText}
          initialValues={{ source: '企业资料粘贴文本', max_facts: 24 }}
        >
          <Form.Item name="source" label="资料来源">
            <Input placeholder="例如：官网介绍、营业执照、资质证书PDF、企业宣传册" />
          </Form.Item>
          <Form.Item
            name="content"
            label="企业资料全文"
            rules={[{ required: true, message: '请粘贴企业资料' }, { min: 20, message: '资料内容太短，无法提取有效事实' }]}
          >
            <TextArea
              rows={12}
              placeholder="把企业介绍、产品资料、资质证书文字、官网内容、课程价格、地址电话、案例等一起粘贴到这里。"
            />
          </Form.Item>
          <Form.Item name="max_facts" label="最多提取条数">
            <Input type="number" min={1} max={50} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加事实Modal */}
      <Modal title="添加品牌事实" open={addFactVisible} onOk={() => factForm.submit()} onCancel={() => setAddFactVisible(false)} width={600}>
        {projectBrands.length > 0 ? (
          <Alert
            message={`将添加到品牌: ${projectBrands[0]?.brand_name || projectBrands[0]?.id}`}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        ) : (
          <Alert
            message="该项目下还没有品牌主体，保存时会自动用项目名称创建一个默认品牌主体"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={factForm} layout="vertical" onFinish={handleAddFact}>
          <Form.Item name="fact_type" label="事实类型" rules={[{ required: true }]}>
            <Input placeholder="例如：qualification, address, price" />
          </Form.Item>
          <Form.Item name="value" label="值" rules={[{ required: true }]}>
            <TextArea rows={2} placeholder="输入事实内容" />
          </Form.Item>
          <Form.Item name="public_wording" label="公开口径">
            <TextArea rows={2} placeholder="对外公开使用的表述（可选）" />
          </Form.Item>
          <Form.Item name="fact_scope" label="公开范围" initialValue="public">
            <Input placeholder="public / internal / restricted" />
          </Form.Item>
          <Form.Item name="source" label="来源">
            <Input placeholder="信息来源" />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" initialValue="low">
            <Input placeholder="low / medium / high" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加信源资产Modal */}
      <Modal
        title="添加信源资产"
        open={addSourceAssetVisible}
        onOk={() => sourceAssetForm.submit()}
        onCancel={() => setAddSourceAssetVisible(false)}
        width={640}
      >
        <Form
          form={sourceAssetForm}
          layout="vertical"
          onFinish={handleAddSourceAsset}
          initialValues={{
            source_type: 'official_site',
            authority_level: 'medium',
            crawlability: 'unknown',
            status: 'active',
          }}
        >
          <Form.Item name="source_type" label="信源类型" rules={[{ required: true, message: '请输入信源类型' }]}>
            <Input placeholder="official_site / qualification / case_page / media_report / knowledge_base" />
          </Form.Item>
          <Form.Item name="platform" label="平台/来源">
            <Input placeholder="例如：官网、微信公众号、人民网、百度百科、民航局公示系统" />
          </Form.Item>
          <Form.Item name="url" label="URL">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="authority_level" label="权威度">
            <Input placeholder="high / medium / low" />
          </Form.Item>
          <Form.Item name="crawlability" label="可抓取性">
            <Input placeholder="crawlable / limited / blocked / unknown" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Input placeholder="active / inactive / pending" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 诊断Modal */}
      <Modal title="资料缺口诊断" open={diagnoseVisible} onOk={handleDiagnose} onCancel={() => setDiagnoseVisible(false)} confirmLoading={gapLoading}>
        <p>请输入已收集的资料字段（用逗号或换行分隔），系统将诊断缺失项：</p>
        <TextArea rows={6} placeholder="例如：&#10;品牌名称&#10;联系电话&#10;地址&#10;资质证书" value={diagnoseFields} onChange={(e) => setDiagnoseFields(e.target.value)} />
      </Modal>

      {/* 添加问题Modal */}
      <Modal
        title={editingQuestion ? '编辑问题' : '添加问题'}
        open={addQuestionVisible}
        onOk={() => questionForm.submit()}
        width={760}
        onCancel={() => {
          setAddQuestionVisible(false);
          setEditingQuestion(null);
          questionForm.resetFields();
        }}
      >
        <Form form={questionForm} layout="vertical" onFinish={handleSaveQuestion}>
          <Form.Item name="question_text" label="问题文本" rules={[{ required: true }]}>
            <TextArea rows={2} placeholder="输入具体的问题文本" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="question_type" label="问题类型" initialValue="brand_reputation">
                <Select
                  options={Object.entries(questionTypeLabels).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sample_policy" label="采样策略" initialValue="mvp">
                <Select
                  options={Object.entries(samplePolicyLabels).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tags" label="标签">
            <Input placeholder="价格、资质、地址、口碑、就业、周末班，多个标签用逗号分隔" />
          </Form.Item>
          <Form.Item name="keyword_breakdown" label="关键词拆解">
            <TextArea rows={2} placeholder="可填写 JSON 或自然语言，例如：地区词、品类词、信任词、价格词" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="keyword_layer" label="关键词层" initialValue="category">
                <Select
                  options={Object.entries(keywordLayerLabels).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="search_asset_type" label="推荐搜索资产" initialValue="faq">
                <Select
                  options={Object.entries(searchAssetTypeLabels).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="question_formula" label="问题公式">
            <Input placeholder="例如：地域词 + 品类词 + 资质核验意图" />
          </Form.Item>
          <Form.Item name="knowledge_need" label="知识需求">
            <TextArea rows={2} placeholder="回答这个问题需要哪些知识资产，例如资质编号、案例、地址、价格、联系方式、对比证据等" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="business_value" label="商业价值" initialValue="medium">
                <Select
                  options={[
                    { value: 'high', label: '高' },
                    { value: 'medium', label: '中' },
                    { value: 'low', label: '低' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="recommended_platforms" label="推荐平台">
                <Input placeholder="baijiahao, zhihu, website" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="evidence_support" label="证据支撑">
            <TextArea rows={2} placeholder="回答这个问题需要哪些事实或信源" />
          </Form.Item>
          <Form.Item name="content_actionability" label="内容可执行性">
            <TextArea rows={2} placeholder="这个问题适合补什么文章、FAQ、官网页或平台版本" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="priority" label="优先级" initialValue={50}>
                <Input type="number" min={1} max={100} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="enabled" label="是否启用" initialValue>
                <Select
                  options={[
                    { value: true, label: '启用' },
                    { value: false, label: '停用' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="focus" label="重点关注" initialValue={false}>
                <Select
                  options={[
                    { value: true, label: '是' },
                    { value: false, label: '否' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
}

export default ProjectDetail;
