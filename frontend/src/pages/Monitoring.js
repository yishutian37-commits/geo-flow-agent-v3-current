import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Col,
  Divider,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  BarChartOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  apiAssetUrl,
  baselineRunsApi,
  modelTargetsApi,
  monitoringApi,
  projectsApi,
  questionsApi,
} from '../services/api';
import Table from '../components/SafeTable';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;
const USER_CANCELLED_MESSAGE = '检测已手动停止';

const panelStyle = {
  background: '#fff',
  border: '1px solid #f0f0f0',
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
};

const compactPanelStyle = {
  background: '#fff',
  border: '1px solid #f0f0f0',
  borderRadius: 8,
  padding: 16,
};

const STATUS_META = {
  running: { color: 'processing', text: '检测中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
};

const LAYER_META = {
  exposure: { color: 'blue', text: '曝光/推荐层' },
  convert: { color: 'purple', text: '转化/承接层' },
  conversion: { color: 'purple', text: '转化/承接层' },
  proof: { color: 'orange', text: '验证/口碑层' },
  verification: { color: 'orange', text: '验证/口碑层' },
  authority: { color: 'gold', text: '权威层' },
  manual: { color: 'default', text: '手动问题' },
};

function extractError(error) {
  const data = error?.response?.data;
  if (data?.detail === '请求参数校验失败' && Array.isArray(data?.errors)) {
    const detail = data.errors
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join('；');
    return detail ? `请求参数校验失败：${detail}` : data.detail;
  }
  if (typeof data?.detail === 'object' && data.detail?.message) {
    return data.detail.message;
  }
  return data?.detail || error?.message || '未知错误';
}

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED'
    || error?.name === 'CanceledError'
    || error?.message === 'canceled'
    || error?.message === 'cancelled';
}

function formatTime(value) {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}

function layerLabel(layer) {
  const key = String(layer || '').toLowerCase();
  const meta = LAYER_META[key] || { color: 'default', text: layer || '未分层' };
  return <Tag color={meta.color}>{meta.text}</Tag>;
}

function statusTag(status) {
  const meta = STATUS_META[status] || { color: 'default', text: status || '未知' };
  return <Tag color={meta.color}>{meta.text}</Tag>;
}

const CONFIDENCE_META = {
  low: { color: 'warning', label: '可信度低', hint: '样本偏少，只能作为快速试跑参考。' },
  medium: { color: 'processing', label: '可信度中', hint: '样本量可以辅助判断，但建议继续扩大检测。' },
  high: { color: 'success', label: '可信度高', hint: '样本量较充分，可作为阶段判断依据。' },
};

function formatPercent(value, digits = 1) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '-';
  return `${Number(value).toFixed(digits)}%`;
}

function metricPoint(data, key) {
  return data?.metrics?.[key]?.point_estimate;
}

function metricInterval(data, key) {
  const item = data?.metrics?.[key];
  if (!item || item.lower === undefined || item.upper === undefined) return '暂无区间';
  return `${formatPercent(item.lower)} - ${formatPercent(item.upper)}`;
}

function buildReadableReport(data) {
  if (!data) return null;
  const sampleCount = data.sample_count || 0;
  const counts = data.raw_counts || {};
  const metrics = data.metrics || {};
  const mention = Number(metricPoint(data, 'brand_mention_rate') || 0);
  const recommend = Number(metricPoint(data, 'recommendation_rate') || 0);
  const negative = Number(metricPoint(data, 'negative_mention_rate') || 0);
  const explicitCitationSamples = counts.explicit_citation_samples || 0;
  const explicitCitations = metrics.total_explicit_citations || 0;
  const confidence = CONFIDENCE_META[data.confidence_level] || CONFIDENCE_META.low;

  let conclusion = 'AI 对品牌的认知还不稳定。';
  let alertType = 'warning';
  if (sampleCount === 0) {
    conclusion = '本次没有有效回答样本，暂时无法判断品牌表现。';
    alertType = 'warning';
  } else if (mention >= 60 && recommend >= 30 && negative === 0) {
    conclusion = 'AI 已经能较稳定地识别品牌，并在部分场景中形成推荐。';
    alertType = 'success';
  } else if (mention >= 30 && recommend < 20) {
    conclusion = 'AI 偶尔知道品牌，但推荐意愿偏弱。';
    alertType = 'warning';
  } else if (mention > 0) {
    conclusion = 'AI 对品牌有零散认知，但还没有形成稳定答案。';
    alertType = 'warning';
  } else {
    conclusion = 'AI 暂未在本轮样本中识别到品牌。';
    alertType = 'error';
  }

  const suggestions = [];
  if (sampleCount > 0 && sampleCount < 30) {
    suggestions.push(`本次只有 ${sampleCount} 个样本，建议至少检测 30 个问题后再做正式判断。`);
  }
  if (mention < 40) {
    suggestions.push('补充品牌基础事实、资质、地址、课程/产品、案例等可公开引用信息。');
  }
  if (recommend < 20) {
    suggestions.push('优先建设“推荐型、对比型、口碑验证型”内容，让 AI 有理由推荐品牌。');
  }
  if (explicitCitationSamples === 0) {
    suggestions.push('增加官网、资质页、案例页、媒体报道等公开信源，提升 AI 引用概率。');
  }
  if (negative > 0) {
    suggestions.push('存在负面提及，需要优先查看原始回答并补充澄清内容。');
  }
  if (!suggestions.length) {
    suggestions.push('保持当前内容节奏，下一轮可扩大样本量并做基线对比。');
  }

  return {
    alertType,
    conclusion,
    confidence,
    sampleCount,
    rows: [
      {
        label: '品牌被提及',
        value: `${counts.mentioned || 0}/${sampleCount}`,
        percent: formatPercent(mention),
        explain: `AI 回答中出现品牌名称或可识别品牌信息的比例，95%区间约 ${metricInterval(data, 'brand_mention_rate')}。`,
      },
      {
        label: '明确推荐',
        value: `${counts.recommended || 0}/${sampleCount}`,
        percent: formatPercent(recommend),
        explain: `AI 不只是提到品牌，而是把品牌作为推荐对象的比例，95%区间约 ${metricInterval(data, 'recommendation_rate')}。`,
      },
      {
        label: '负面提及',
        value: `${counts.negative || 0}/${sampleCount}`,
        percent: formatPercent(negative),
        explain: `AI 回答中出现负面评价、风险提示或不利描述的比例。`,
      },
      {
        label: '引用线索',
        value: `${explicitCitationSamples}/${sampleCount}`,
        percent: formatPercent(metricPoint(data, 'explicit_citation_rate')),
        explain: `有 ${explicitCitationSamples} 个回答出现明确来源线索，合计识别到 ${explicitCitations} 次引用。`,
      },
    ],
    suggestions,
  };
}

function pickMechanism(target) {
  const raw = target?.supported_mechanisms || '';
  const match = String(raw).match(/[ABCDE]/i);
  return match ? match[0].toUpperCase() : 'B';
}

function sourceCategoryColor(category) {
  return {
    owned_asset: 'green',
    authority: 'gold',
    search_engine: 'orange',
    media_platform: 'blue',
    third_party: 'default',
    unknown: 'default',
  }[category] || 'default';
}

function calcRate(part, total) {
  if (!total) return 0;
  return Number(((Number(part || 0) / Number(total || 0)) * 100).toFixed(1));
}

function sampleDayKey(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) {
    return { key: 'unknown', label: '未知日期', time: 0 };
  }
  const key = date.toISOString().slice(0, 10);
  return {
    key,
    label: `${date.getMonth() + 1}/${date.getDate()}`,
    time: date.getTime(),
  };
}

function Monitoring() {
  const [activeTab, setActiveTab] = useState('start');
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState([]);
  const [samples, setSamples] = useState([]);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleDetail, setSampleDetail] = useState(null);
  const [sourceAnalysis, setSourceAnalysis] = useState(null);
  const [sourceAnalysisLoading, setSourceAnalysisLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [modelTargets, setModelTargets] = useState([]);
  const [allTargets, setAllTargets] = useState([]);
  const [targetLoading, setTargetLoading] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [questionMode, setQuestionMode] = useState('smart');
  const [selectedQuestionIds, setSelectedQuestionIds] = useState([]);
  const [selectedTargetIds, setSelectedTargetIds] = useState([]);
  const [waitSeconds, setWaitSeconds] = useState(60);
  const [manualQuestions, setManualQuestions] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [stoppingDetection, setStoppingDetection] = useState(false);
  const [detectProgress, setDetectProgress] = useState({
    total: 0,
    done: 0,
    current: '',
    logs: [],
  });
  const [targetModalVisible, setTargetModalVisible] = useState(false);
  const [editingTarget, setEditingTarget] = useState(null);
  const [targetForm] = Form.useForm();
  const targetRecognitionMode = Form.useWatch('recognition_mode', targetForm) || 'text';
  const [reportModalVisible, setReportModalVisible] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [promotingBaselineRunId, setPromotingBaselineRunId] = useState(null);
  const [creatingTaskSampleId, setCreatingTaskSampleId] = useState(null);
  const [savingReviewSampleId, setSavingReviewSampleId] = useState(null);
  const cancelRequestedRef = useRef(false);
  const activeAbortControllerRef = useRef(null);
  const activeRunIdRef = useRef(null);

  const projectById = useMemo(() => {
    const map = {};
    projects.forEach((item) => {
      map[item.id] = item;
    });
    return map;
  }, [projects]);
  const selectedProject = projectById[selectedProjectId];

  const targetById = useMemo(() => {
    const map = {};
    [...allTargets, ...modelTargets].forEach((item) => {
      map[item.id] = item;
    });
    return map;
  }, [allTargets, modelTargets]);

  const filteredRuns = useMemo(() => {
    if (!selectedProjectId) return runs;
    return runs.filter((item) => item.project_id === selectedProjectId);
  }, [runs, selectedProjectId]);

  const filteredSamples = useMemo(() => {
    if (!selectedProjectId) return samples;
    return samples.filter((item) => item.project_id === selectedProjectId);
  }, [samples, selectedProjectId]);

  const smartQuestions = useMemo(() => {
    const layerWeight = {
      exposure: 5,
      convert: 4,
      conversion: 4,
      proof: 3,
      verification: 3,
      authority: 2,
      manual: 0,
    };
    return [...questions]
      .sort((a, b) => {
        const aw = layerWeight[String(a.layer || '').toLowerCase()] || 1;
        const bw = layerWeight[String(b.layer || '').toLowerCase()] || 1;
        if (Boolean(b.focus) !== Boolean(a.focus)) return Boolean(b.focus) ? 1 : -1;
        if (bw !== aw) return bw - aw;
        return (b.priority || 0) - (a.priority || 0);
      })
      .slice(0, 9);
  }, [questions]);

  const currentQuestionIds = useMemo(() => {
    if (questionMode === 'smart') return smartQuestions.map((item) => item.id);
    if (questionMode === 'library') return selectedQuestionIds;
    return [];
  }, [questionMode, selectedQuestionIds, smartQuestions]);

  const selectedTargets = useMemo(
    () => modelTargets.filter((item) => selectedTargetIds.includes(item.id)),
    [modelTargets, selectedTargetIds]
  );

  const stats = useMemo(() => {
    const sampleTotal = filteredSamples.length || filteredRuns.reduce((sum, item) => sum + (item.sample_count || 0), 0);
    const sampleTimes = filteredSamples
      .map((item) => item.sampled_at)
      .filter(Boolean)
      .sort();
    return {
      runs: filteredRuns.length,
      samples: sampleTotal,
      completed: filteredRuns.filter((item) => item.status === 'completed').length,
      targets: modelTargets.length,
      questions: questions.length,
      latestSampleAt: sampleTimes.length ? sampleTimes[sampleTimes.length - 1] : null,
    };
  }, [filteredRuns, filteredSamples, modelTargets, questions]);

  const platformPerformance = useMemo(() => {
    const map = {};
    filteredSamples.forEach((sample) => {
      const target = targetById[sample.model_target_id];
      const platform = sample.model_target_name || target?.product_name || '未知平台';
      if (!map[platform]) {
        map[platform] = {
          platform,
          sample_count: 0,
          mentioned_count: 0,
          recommended_count: 0,
          source_sample_count: 0,
          source_count: 0,
          owned_source_samples: 0,
        };
      }
      const item = map[platform];
      const sources = Array.isArray(sample.sources) ? sample.sources : [];
      const sourceCount = Number(sample.source_count || sources.length || 0);
      item.sample_count += 1;
      item.source_count += sourceCount;
      if (sample.brand_mentioned) item.mentioned_count += 1;
      if (sample.recommended) item.recommended_count += 1;
      if (sourceCount > 0) item.source_sample_count += 1;
      if (sources.some((source) => source?.is_own_asset || source?.category === 'owned_asset')) {
        item.owned_source_samples += 1;
      }
    });

    return Object.values(map)
      .map((item) => ({
        ...item,
        mention_rate: calcRate(item.mentioned_count, item.sample_count),
        recommendation_rate: calcRate(item.recommended_count, item.sample_count),
        source_coverage_rate: calcRate(item.source_sample_count, item.sample_count),
        owned_source_rate: calcRate(item.owned_source_samples, item.sample_count),
      }))
      .sort((a, b) => {
        if (b.recommendation_rate !== a.recommendation_rate) return b.recommendation_rate - a.recommendation_rate;
        if (b.mention_rate !== a.mention_rate) return b.mention_rate - a.mention_rate;
        return b.sample_count - a.sample_count;
      });
  }, [filteredSamples, targetById]);

  const trendRows = useMemo(() => {
    const map = {};
    filteredSamples.forEach((sample) => {
      const day = sampleDayKey(sample.sampled_at);
      if (!map[day.key]) {
        map[day.key] = {
          key: day.key,
          label: day.label,
          time: day.time,
          sample_count: 0,
          mentioned_count: 0,
          recommended_count: 0,
          source_sample_count: 0,
        };
      }
      const item = map[day.key];
      const sources = Array.isArray(sample.sources) ? sample.sources : [];
      const sourceCount = Number(sample.source_count || sources.length || 0);
      item.sample_count += 1;
      if (sample.brand_mentioned) item.mentioned_count += 1;
      if (sample.recommended) item.recommended_count += 1;
      if (sourceCount > 0) item.source_sample_count += 1;
    });

    return Object.values(map)
      .map((item) => ({
        ...item,
        mention_rate: calcRate(item.mentioned_count, item.sample_count),
        recommendation_rate: calcRate(item.recommended_count, item.sample_count),
        source_coverage_rate: calcRate(item.source_sample_count, item.sample_count),
      }))
      .sort((a, b) => a.time - b.time)
      .slice(-14);
  }, [filteredSamples]);

  const loadProjects = async () => {
    const res = await projectsApi.list({ limit: 100 });
    const data = res.data || [];
    setProjects(data);
    if (!selectedProjectId && data.length > 0) {
      setSelectedProjectId(data[0].id);
    }
  };

  const loadRuns = async () => {
    const res = await monitoringApi.listRuns({ limit: 200 });
    setRuns(res.data || []);
  };

  const loadSamples = async (projectId = selectedProjectId) => {
    setSampleLoading(true);
    try {
      const params = { limit: 500 };
      if (projectId) params.project_id = projectId;
      const res = await monitoringApi.listSamples(params);
      setSamples(res.data || []);
    } finally {
      setSampleLoading(false);
    }
  };

  const loadSourceAnalysis = async (projectId = selectedProjectId) => {
    if (!projectId) {
      setSourceAnalysis(null);
      return;
    }
    setSourceAnalysisLoading(true);
    try {
      const res = await monitoringApi.sourceAnalysis({ project_id: projectId, limit: 1000 });
      setSourceAnalysis(res.data || null);
    } catch (error) {
      setSourceAnalysis(null);
    } finally {
      setSourceAnalysisLoading(false);
    }
  };

  const loadAllTargets = async () => {
    const res = await modelTargetsApi.list({ limit: 1000 });
    setAllTargets(res.data || []);
  };

  const loadModelTargets = async (projectId) => {
    if (!projectId) {
      setModelTargets([]);
      setSelectedTargetIds([]);
      return;
    }
    setTargetLoading(true);
    try {
      const res = await modelTargetsApi.list({ project_id: projectId, limit: 100 });
      const data = res.data || [];
      setModelTargets(data);
      setSelectedTargetIds(data.map((item) => item.id));
    } catch (error) {
      setModelTargets([]);
      setSelectedTargetIds([]);
      message.error('加载检测平台失败：' + extractError(error));
    } finally {
      setTargetLoading(false);
    }
  };

  const loadQuestions = async (projectId) => {
    if (!projectId) {
      setQuestions([]);
      setSelectedQuestionIds([]);
      return;
    }
    try {
      const res = await questionsApi.listGroups({ project_id: projectId });
      const groups = res.data || [];
      const flat = groups.flatMap((group) => (
        (group.questions || []).filter((question) => question.enabled !== false).map((question) => ({
          ...question,
          layer: group.layer,
          group_intent_name: group.intent_name,
          representative_question: group.representative_question,
        }))
      ));
      setQuestions(flat);
    } catch (error) {
      setQuestions([]);
      setSelectedQuestionIds([]);
      message.error('加载问题库失败：' + extractError(error));
    }
  };

  const refreshAll = async () => {
    setLoading(true);
    try {
      await Promise.all([loadProjects(), loadRuns(), loadAllTargets(), loadSamples(), loadSourceAnalysis()]);
    } catch (error) {
      message.error('加载监测数据失败：' + extractError(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    loadModelTargets(selectedProjectId);
    loadQuestions(selectedProjectId);
    loadSamples(selectedProjectId);
    loadSourceAnalysis(selectedProjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  useEffect(() => {
    if (questionMode === 'smart') {
      setSelectedQuestionIds(smartQuestions.map((item) => item.id));
    }
  }, [questionMode, smartQuestions]);

  const appendProgressLog = (log) => {
    setDetectProgress((prev) => ({
      ...prev,
      logs: [log, ...prev.logs].slice(0, 10),
    }));
  };

  const markActiveRunStatus = async (status) => {
    const runId = activeRunIdRef.current;
    if (!runId) return;
    try {
      await monitoringApi.updateRunStatus(runId, status);
    } catch (error) {
      appendProgressLog({
        type: 'warning',
        text: `检测记录状态同步失败：${extractError(error)}`,
      });
    }
  };

  const throwIfCancelled = () => {
    if (cancelRequestedRef.current) {
      throw new Error(USER_CANCELLED_MESSAGE);
    }
  };

  const handleStopDetection = () => {
    if (!detecting) return;
    cancelRequestedRef.current = true;
    setStoppingDetection(true);
    if (activeAbortControllerRef.current) {
      activeAbortControllerRef.current.abort();
    }
    setDetectProgress((prev) => ({
      ...prev,
      current: '正在停止检测，当前题结束后不会继续下一题',
    }));
    appendProgressLog({
      type: 'warning',
      text: '已请求停止检测：系统会中断当前等待，并且不会继续打开下一题。',
    });
  };

  const createManualQuestions = async () => {
    const lines = manualQuestions
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (lines.length === 0) return [];

    const groupRes = await questionsApi.createGroup({
      project_id: selectedProjectId,
      layer: 'manual',
      intent_name: `手动检测问题 ${new Date().toLocaleString()}`,
      representative_question: lines[0],
      priority: 80,
      status: 'archived',
    });
    const group = groupRes.data;
    const created = [];
    for (const line of lines) {
      const res = await questionsApi.createQuestion(group.id, {
        group_id: group.id,
        question_text: line,
        priority: 80,
        sample_policy: 'mvp',
      });
      created.push({
        ...res.data,
        layer: 'manual',
        group_intent_name: group.intent_name,
        representative_question: group.representative_question,
      });
    }
    await loadQuestions(selectedProjectId);
    return created;
  };

  const prepareDetectionQuestions = async () => {
    if (questionMode === 'manual') {
      return createManualQuestions();
    }
    if (questionMode === 'smart') return smartQuestions;
    return questions.filter((item) => selectedQuestionIds.includes(item.id));
  };

  const handleStartDetection = async () => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    if (selectedTargets.length === 0) {
      message.warning('请至少选择一个检测平台');
      return;
    }
    if (questionMode !== 'manual' && currentQuestionIds.length === 0) {
      message.warning('当前项目还没有可检测的问题，请先生成问题库或手动输入问题');
      return;
    }
    if (questionMode === 'manual' && manualQuestions.trim().length === 0) {
      message.warning('请输入要检测的问题，每行一个');
      return;
    }

    setDetecting(true);
    setStoppingDetection(false);
    cancelRequestedRef.current = false;
    activeAbortControllerRef.current = null;
    setDetectProgress({ total: 0, done: 0, current: '准备检测问题', logs: [] });
    let done = 0;
    try {
      const detectionQuestions = await prepareDetectionQuestions();
      throwIfCancelled();
      const questionIds = detectionQuestions.map((item) => item.id);
      const questionMap = {};
      [...questions, ...smartQuestions, ...detectionQuestions].forEach((item) => {
        questionMap[item.id] = item;
      });
      if (questionMode === 'manual') {
        await loadQuestions(selectedProjectId);
      }

      const total = questionIds.length * selectedTargets.length;
      setDetectProgress({ total, done: 0, current: '正在创建检测记录', logs: [] });
      try {
        const bridgeStatus = await monitoringApi.webbridgeStatus();
        if (bridgeStatus.data?.provider_name || bridgeStatus.data?.bridge_provider) {
          appendProgressLog({
            type: 'info',
            text: `WebBridge 当前使用：${bridgeStatus.data.provider_name || bridgeStatus.data.bridge_provider}`,
          });
        }
        if (bridgeStatus.data?.warning) {
          appendProgressLog({
            type: 'warning',
            text: bridgeStatus.data.warning,
          });
        }
      } catch (error) {
        appendProgressLog({
          type: 'warning',
          text: `WebBridge 状态预检失败，但将继续尝试自动检测：${extractError(error)}`,
        });
      }

      for (const target of selectedTargets) {
        throwIfCancelled();
        const runRes = await monitoringApi.createRun({
          project_id: selectedProjectId,
          run_type: 'web_auto',
          mechanism_type: pickMechanism(target),
          model_target_id: target.id,
          sample_policy: 'mvp',
          call_mode_detail: 'WebBridge 自动打开网页并提问',
        });
        const run = runRes.data;
        activeRunIdRef.current = run.id;
        let successCount = 0;

        for (const questionId of questionIds) {
          throwIfCancelled();
          const question = questionMap[questionId] || questions.find((item) => item.id === questionId);
          const questionText = question?.question_text || questionId;
          setDetectProgress((prev) => ({
            ...prev,
            current: `${target.product_name}：${questionText}`,
          }));
          let countedSample = false;
          try {
            const controller = new AbortController();
            activeAbortControllerRef.current = controller;
            const res = await monitoringApi.webbridgeSample(run.id, {
              question_id: questionId,
              wait_seconds: waitSeconds,
              create_sample: true,
            }, {
              signal: controller.signal,
            });
            activeAbortControllerRef.current = null;
            throwIfCancelled();
            if (res.data?.status_warning) {
              appendProgressLog({
                type: 'warning',
                text: res.data.status_warning,
              });
            }
            if (res.data?.bridge_provider) {
              appendProgressLog({
                type: 'info',
                text: `本次网页提问桥接：${res.data.bridge_provider}`,
              });
            }
            successCount += 1;
            appendProgressLog({
              type: 'success',
              text: `${target.product_name} 已完成：${questionText}`,
            });
            countedSample = true;
          } catch (error) {
            activeAbortControllerRef.current = null;
            if (cancelRequestedRef.current || isAbortError(error)) {
              appendProgressLog({
                type: 'warning',
                text: `${target.product_name} 已停止：${questionText}`,
              });
              throw new Error(USER_CANCELLED_MESSAGE);
            }
            const errorText = extractError(error);
            appendProgressLog({
              type: 'error',
              text: `${target.product_name} 失败：${questionText}｜${errorText}`,
            });
            countedSample = true;
            throw new Error(`${target.product_name} 自动提问失败，已停止后续检测：${errorText}`);
          } finally {
            if (countedSample) {
              const nextDone = done + 1;
              done = nextDone;
              setDetectProgress((prev) => ({ ...prev, done: nextDone }));
            }
          }
        }

        throwIfCancelled();
        try {
          await monitoringApi.calculateMetrics(run.id);
          if (successCount > 0) {
            await monitoringApi.generateRecommendations(run.id).catch(() => null);
          }
          activeRunIdRef.current = null;
        } catch (error) {
          appendProgressLog({
            type: 'error',
            text: `${target.product_name} 指标计算失败：${extractError(error)}`,
          });
        }
      }

      await Promise.all([loadRuns(), loadAllTargets(), loadSamples(selectedProjectId), loadSourceAnalysis(selectedProjectId)]);
      setActiveTab('records');
      message.success('检测完成，已生成检测记录');
    } catch (error) {
      if (error?.message === USER_CANCELLED_MESSAGE || cancelRequestedRef.current) {
        await markActiveRunStatus('cancelled');
        message.warning('检测已停止，不会继续打开下一题');
      } else {
        await markActiveRunStatus('failed');
        message.error('启动检测失败：' + extractError(error));
      }
    } finally {
      const cancelled = cancelRequestedRef.current;
      activeAbortControllerRef.current = null;
      activeRunIdRef.current = null;
      setDetecting(false);
      setStoppingDetection(false);
      setDetectProgress((prev) => ({ ...prev, current: cancelled ? '检测已停止' : '检测结束' }));
    }
  };

  const openTargetModal = (target = null) => {
    const existingTarget = target && target.id ? target : null;
    setEditingTarget(existingTarget);
    targetForm.resetFields();
    if (existingTarget) {
      targetForm.setFieldsValue({
        ...existingTarget,
        supported_mechanisms: existingTarget.supported_mechanisms
          ? String(existingTarget.supported_mechanisms).split(',').map((item) => item.trim()).filter(Boolean)
          : ['B'],
        access_method: existingTarget.access_method || 'webbridge',
        recognition_mode: existingTarget.recognition_mode || 'text',
      });
    } else {
      targetForm.setFieldsValue({
        project_id: selectedProjectId,
        supported_mechanisms: ['B'],
        access_method: 'webbridge',
        recognition_mode: 'text',
        search_backend_confidence: 'medium',
        api_available: false,
      });
    }
    setTargetModalVisible(true);
  };

  const handleSubmitTarget = async (values) => {
    try {
      const payload = {
        ...values,
        project_id: values.project_id || selectedProjectId,
        supported_mechanisms: Array.isArray(values.supported_mechanisms)
          ? values.supported_mechanisms.join(',')
          : values.supported_mechanisms,
        api_available: false,
        search_backend_confidence: values.search_backend_confidence || 'medium',
        recognition_mode: values.recognition_mode === 'vision' ? 'vision' : 'text',
      };
      if (editingTarget) {
        await modelTargetsApi.update(editingTarget.id, payload);
        message.success('检测平台已更新');
      } else {
        await modelTargetsApi.create(payload);
        message.success('检测平台已添加');
      }
      setTargetModalVisible(false);
      setEditingTarget(null);
      await Promise.all([loadModelTargets(payload.project_id), loadAllTargets()]);
    } catch (error) {
      message.error((editingTarget ? '更新' : '添加') + '检测平台失败：' + extractError(error));
    }
  };

  const handleDeleteTarget = (target) => {
    Modal.confirm({
      title: '删除检测平台',
      content: `确定删除「${target.product_name}」吗？如果它已经被检测记录或基线引用，需要先删除相关记录。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await modelTargetsApi.delete(target.id);
          message.success('检测平台已删除');
          await Promise.all([loadModelTargets(target.project_id), loadAllTargets()]);
        } catch (error) {
          message.error('删除检测平台失败：' + extractError(error));
        }
      },
    });
  };

  const handleDeleteRun = (run) => {
    Modal.confirm({
      title: '删除检测记录',
      content: '删除后会同时删除这次检测下的回答样本和情绪记录，是否继续？',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await monitoringApi.deleteRun(run.id);
          message.success('检测记录已删除');
          await loadRuns();
        } catch (error) {
          message.error('删除检测记录失败：' + extractError(error));
        }
      },
    });
  };

  const handleDeleteSample = (sample) => {
    Modal.confirm({
      title: '删除检测明细',
      content: `确定删除「${sample.question_text || '该问题'}」在「${sample.model_target_name || '该平台'}」上的这条检测结果吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await monitoringApi.deleteSample(sample.id);
          message.success('检测明细已删除');
          if (sampleDetail?.id === sample.id) {
            setSampleDetail(null);
          }
          await Promise.all([
            loadSamples(selectedProjectId),
            loadRuns(),
            selectedProjectId ? loadSourceAnalysis(selectedProjectId) : Promise.resolve(),
          ]);
        } catch (error) {
          message.error('删除检测明细失败：' + extractError(error));
        }
      },
    });
  };

  const handleCreateTaskFromSample = async (sample) => {
    setCreatingTaskSampleId(sample.id);
    try {
      const res = await monitoringApi.createContentTaskFromSample(sample.id, {});
      if (res.data?.task?.already_exists) {
        message.info('这条检测短板已有关联内容任务，未重复创建');
      } else {
        message.success('已从检测明细生成内容任务');
      }
    } catch (error) {
      message.error('生成内容任务失败：' + extractError(error));
    } finally {
      setCreatingTaskSampleId(null);
    }
  };

  const handleSaveSampleReviewKnowledge = async (sample) => {
    setSavingReviewSampleId(sample.id);
    try {
      await monitoringApi.createReviewKnowledgeFromSample(sample.id, {
        notes: sample.brand_mentioned
          ? '复盘该回答的提及、推荐、来源和内容缺口，供后续问题矩阵与内容任务参考。'
          : '复盘该回答未识别品牌的原因，供后续补充入池内容和公开信源参考。',
      });
      message.success('已沉淀为项目知识库复盘资料');
      await Promise.all([
        selectedProjectId ? loadSourceAnalysis(selectedProjectId) : Promise.resolve(),
        loadSamples(selectedProjectId),
      ]);
    } catch (error) {
      message.error('沉淀复盘资料失败：' + extractError(error));
    } finally {
      setSavingReviewSampleId(null);
    }
  };

  const handleViewMetrics = async (run) => {
    setSelectedRun(run);
    setReportData(null);
    setReportModalVisible(true);
    setReportLoading(true);
    try {
      const res = await monitoringApi.calculateMetrics(run.id);
      setReportData(res.data);
      await loadRuns();
    } catch (error) {
      message.error('计算检测结果失败：' + extractError(error));
    } finally {
      setReportLoading(false);
    }
  };

  const handleGenerateRecommendations = async (run) => {
    try {
      const res = await monitoringApi.generateRecommendations(run.id);
      message.success(`已生成 ${res.data?.created_recommendations || 0} 条优化建议`);
    } catch (error) {
      message.error('生成优化建议失败：' + extractError(error));
    }
  };

  const handlePromoteBaseline = async (run) => {
    setPromotingBaselineRunId(run.id);
    try {
      const res = await baselineRunsApi.promoteFromRun(run.id, { require_acceptance_grade: false });
      message.success(`已设为基线：新增 ${res.data?.created_baselines || 0} 条，跳过 ${res.data?.skipped_existing || 0} 条`);
    } catch (error) {
      message.error('设为基线失败：' + extractError(error));
    } finally {
      setPromotingBaselineRunId(null);
    }
  };

  const handleUseRunSetup = async (run) => {
    setSelectedProjectId(run.project_id);
    setSelectedTargetIds([run.model_target_id]);
    setQuestionMode('smart');
    setActiveTab('start');
    message.info('已带入项目和检测平台，可直接开始新一轮检测');
  };

  const questionColumns = [
    {
      title: '问题',
      dataIndex: 'question_text',
      width: 420,
      ellipsis: true,
      render: (value, record) => (
        <Space direction="vertical" size={2}>
          <Space wrap>
            {record.focus && <Tag color="red">重点</Tag>}
            <Text>{value}</Text>
          </Space>
          {record.tags && <Text type="secondary">{record.tags}</Text>}
        </Space>
      ),
    },
    {
      title: '层级',
      dataIndex: 'layer',
      width: 150,
      render: layerLabel,
    },
    {
      title: '意图',
      dataIndex: 'group_intent_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 100,
    },
    {
      title: '采样',
      dataIndex: 'sample_policy',
      width: 110,
      render: (value) => <Tag>{value || 'mvp'}</Tag>,
    },
  ];

  const targetColumns = [
    {
      title: '平台名称',
      dataIndex: 'product_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: '网页地址',
      dataIndex: 'web_url',
      width: 360,
      ellipsis: true,
      render: (value) => value || '-',
    },
    {
      title: '调用方式',
      dataIndex: 'access_method',
      width: 140,
      render: (value) => <Tag>{value || 'webbridge'}</Tag>,
    },
    {
      title: '识别模式',
      dataIndex: 'recognition_mode',
      width: 140,
      render: (value) => (
        <Tag color={value === 'vision' ? 'purple' : 'blue'}>
          {value === 'vision' ? '视觉识别' : '文本抓取'}
        </Tag>
      ),
    },
    {
      title: '机制',
      dataIndex: 'supported_mechanisms',
      width: 120,
      render: (value) => value || 'B',
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openTargetModal(record)}>
            编辑
          </Button>
          <Button danger type="link" icon={<DeleteOutlined />} onClick={() => handleDeleteTarget(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const runColumns = [
    {
      title: '检测对象',
      key: 'target',
      width: 360,
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text strong ellipsis style={{ maxWidth: 330 }}>
            {projectById[record.project_id]?.name || record.project_id}
          </Text>
          <Text type="secondary" ellipsis style={{ maxWidth: 330 }}>
            {targetById[record.model_target_id]?.product_name || record.model_target_id}
          </Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: statusTag,
    },
    {
      title: '样本数',
      dataIndex: 'sample_count',
      width: 100,
      render: (value) => value || 0,
    },
    {
      title: '检测方式',
      dataIndex: 'call_mode_detail',
      width: 260,
      ellipsis: true,
      render: (value) => value || '手动记录',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 190,
      render: formatTime,
    },
    {
      title: '操作',
      key: 'action',
      width: 360,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewMetrics(record)}>
            结果
          </Button>
          <Button type="link" icon={<BarChartOutlined />} onClick={() => handleGenerateRecommendations(record)}>
            建议
          </Button>
          <Button
            type="link"
            loading={promotingBaselineRunId === record.id}
            onClick={() => handlePromoteBaseline(record)}
          >
            设为基线
          </Button>
          <Button type="link" onClick={() => handleUseRunSetup(record)}>
            再测
          </Button>
          <Button danger type="link" icon={<DeleteOutlined />} onClick={() => handleDeleteRun(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const sampleColumns = [
    {
      title: '问题',
      dataIndex: 'question_text',
      width: 360,
      ellipsis: true,
      render: (value) => value || '-',
    },
    {
      title: '平台',
      dataIndex: 'model_target_name',
      width: 150,
      ellipsis: true,
      render: (value, record) => value || targetById[record.model_target_id]?.product_name || '-',
    },
    {
      title: '提及品牌',
      dataIndex: 'brand_mentioned',
      width: 110,
      render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '已提及' : '未提及'}</Tag>,
    },
    {
      title: '推荐状态',
      dataIndex: 'recommended',
      width: 110,
      render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '已推荐' : '未推荐'}</Tag>,
    },
    {
      title: '情绪',
      dataIndex: ['analysis', 'sentiment_label'],
      width: 120,
      render: (value, record) => (
        <Tag color={record.analysis?.sentiment === 'negative' ? 'red' : record.analysis?.sentiment === 'positive' ? 'green' : 'blue'}>
          {value || '-'}
        </Tag>
      ),
    },
    {
      title: '信息来源',
      dataIndex: 'source_count',
      width: 110,
      render: (value, record) => {
        const count = Number(value || record.sources?.length || 0);
        return <Tag color={count > 0 ? 'blue' : 'default'}>{count} 条</Tag>;
      },
    },
    {
      title: '补发建议',
      dataIndex: 'content_recommendation',
      width: 280,
      render: (value) => {
        if (!value) return <Text type="secondary">-</Text>;
        return (
          <Space direction="vertical" size={4}>
            <Text type="secondary">{value.reason}</Text>
            <Space wrap size={4}>
              {(value.recommended_platforms || []).slice(0, 4).map((platform) => (
                <Tag key={platform} color="cyan">{platform}</Tag>
              ))}
              {value.business_value && (
                <Tag color={value.business_value === 'high' ? 'red' : 'orange'}>价值：{value.business_value}</Tag>
              )}
            </Space>
            {value.content_actionability && (
              <Text type="secondary" ellipsis style={{ maxWidth: 240 }}>{value.content_actionability}</Text>
            )}
          </Space>
        );
      },
    },
    {
      title: '检测时间',
      dataIndex: 'sampled_at',
      width: 190,
      render: formatTime,
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button type="link" icon={<EyeOutlined />} onClick={() => setSampleDetail(record)}>
            AI搜索详情
          </Button>
          <Button
            type="link"
            icon={<ThunderboltOutlined />}
            loading={creatingTaskSampleId === record.id}
            onClick={() => handleCreateTaskFromSample(record)}
          >
            生成任务
          </Button>
          <Button danger type="link" icon={<DeleteOutlined />} onClick={() => handleDeleteSample(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const renderProjectSelector = () => (
    <Space direction="vertical" style={{ width: '100%' }} size={8}>
      <Text strong>项目</Text>
      <Select
        value={selectedProjectId}
        onChange={setSelectedProjectId}
        style={{ width: '100%' }}
        placeholder="选择要检测的项目"
        options={projects.map((item) => ({ label: item.name, value: item.id }))}
      />
    </Space>
  );

  const renderStartTab = () => (
    <div>
      <div style={panelStyle}>
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={8}>
            {renderProjectSelector()}
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              先选项目，系统会自动读取该项目的问题库和检测平台。
            </Paragraph>
          </Col>
          <Col xs={24} lg={16}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text strong>检测平台</Text>
                <Button size="small" icon={<PlusOutlined />} onClick={() => openTargetModal()}>
                  添加平台
                </Button>
              </Space>
              <Spin spinning={targetLoading}>
                {modelTargets.length === 0 ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="当前项目还没有检测平台"
                    description="先添加 Kimi、豆包、DeepSeek 等 AI 网页地址，才能执行自动检测。"
                  />
                ) : (
                  <Checkbox.Group
                    value={selectedTargetIds}
                    onChange={setSelectedTargetIds}
                    style={{ width: '100%' }}
                  >
                    <Row gutter={[12, 12]}>
                      {modelTargets.map((target) => (
                        <Col xs={24} md={12} xl={8} key={target.id}>
                          <div style={compactPanelStyle}>
                            <Checkbox value={target.id}>
                              <Text strong>{target.product_name}</Text>
                            </Checkbox>
                            <div style={{ marginTop: 6 }}>
                              <Tag color={target.recognition_mode === 'vision' ? 'purple' : 'blue'}>
                                {target.recognition_mode === 'vision' ? '视觉识别' : '文本抓取'}
                              </Tag>
                            </div>
                            <div style={{ marginTop: 8 }}>
                              <Text type="secondary" ellipsis style={{ maxWidth: '100%' }}>
                                {target.web_url || '未配置网页地址'}
                              </Text>
                            </div>
                          </div>
                        </Col>
                      ))}
                    </Row>
                  </Checkbox.Group>
                )}
              </Spin>
            </Space>
          </Col>
        </Row>
      </div>

      <div style={panelStyle}>
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div>
              <Text strong>检测问题</Text>
              <div>
                <Text type="secondary">推荐默认用智能推荐；需要精确检测时再从问题库勾选。</Text>
              </div>
            </div>
            <Radio.Group value={questionMode} onChange={(event) => setQuestionMode(event.target.value)}>
              <Radio.Button value="smart">智能推荐</Radio.Button>
              <Radio.Button value="library">从问题库选择</Radio.Button>
              <Radio.Button value="manual">手动输入</Radio.Button>
            </Radio.Group>
          </Space>

          {questionMode === 'smart' && (
            <div>
              <Alert
                type={smartQuestions.length ? 'info' : 'warning'}
                showIcon
                message={smartQuestions.length ? `已自动挑选 ${smartQuestions.length} 个高优先级问题` : '当前项目没有可用问题'}
                description={smartQuestions.length ? '系统优先覆盖曝光推荐、转化承接、验证口碑等 GEO 关键层级。' : '请先在项目详情页生成问题库，或切换到手动输入。'}
              />
              {smartQuestions.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {smartQuestions.map((question) => (
                      <div key={question.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                        {layerLabel(question.layer)}
                        <Text>{question.question_text}</Text>
                      </div>
                    ))}
                  </Space>
                </div>
              )}
            </div>
          )}

          {questionMode === 'library' && (
            <Table
              rowKey="id"
              columns={questionColumns}
              dataSource={questions}
              pagination={{ pageSize: 8 }}
              rowSelection={{
                selectedRowKeys: selectedQuestionIds,
                onChange: setSelectedQuestionIds,
              }}
              locale={{ emptyText: '暂无问题，请先生成问题库' }}
            />
          )}

          {questionMode === 'manual' && (
            <TextArea
              value={manualQuestions}
              onChange={(event) => setManualQuestions(event.target.value)}
              rows={6}
              placeholder={'每行输入一个要检测的问题，例如：\n包头哪家无人机执照培训机构靠谱？\n蒙霁无人机培训通过率怎么样？'}
            />
          )}
        </Space>
      </div>

      <div style={panelStyle}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={8}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text strong>最长等待时间</Text>
              <Select
                value={waitSeconds}
                onChange={setWaitSeconds}
                style={{ width: '100%' }}
                options={[
                  { label: '30 秒：极短问题', value: 30 },
                  { label: '60 秒：默认推荐', value: 60 },
                  { label: '90 秒：复杂问题', value: 90 },
                  { label: '120 秒：长回答', value: 120 },
                  { label: '180 秒：慢速平台', value: 180 },
                  { label: '240 秒：超长回答', value: 240 },
                ]}
              />
              <Text type="secondary">系统会等到回答连续稳定后再进入下一题，超过该时间才强制抓取。</Text>
            </Space>
          </Col>
          <Col xs={24} lg={16}>
            <Space size={12} wrap style={{ justifyContent: 'flex-end', width: '100%' }}>
              <Button icon={<ReloadOutlined />} onClick={refreshAll} disabled={detecting}>
                刷新
              </Button>
              <Button
                type="primary"
                size="large"
                icon={<ThunderboltOutlined />}
                loading={detecting}
                onClick={handleStartDetection}
                disabled={detecting}
              >
                开始自动检测
              </Button>
              {detecting && (
                <Button
                  danger
                  size="large"
                  icon={<StopOutlined />}
                  loading={stoppingDetection}
                  onClick={handleStopDetection}
                >
                  停止检测
                </Button>
              )}
            </Space>
          </Col>
        </Row>

        {(detecting || detectProgress.total > 0) && (
          <>
            <Divider />
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Progress
                percent={detectProgress.total ? Math.round((detectProgress.done / detectProgress.total) * 100) : 0}
                status={detecting ? 'active' : 'normal'}
              />
              <Text type="secondary">{detectProgress.current}</Text>
              {detectProgress.logs.length > 0 && (
                <Space direction="vertical" style={{ width: '100%' }} size={6}>
                  {detectProgress.logs.map((log, index) => (
                    <Alert
                      key={`${log.text}-${index}`}
                      type={log.type === 'error' ? 'error' : log.type === 'warning' ? 'warning' : 'success'}
                      showIcon
                      message={log.text}
                    />
                  ))}
                </Space>
              )}
            </Space>
          </>
        )}
      </div>
    </div>
  );

  const renderRecordsTab = () => (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} lg={6}>
          <div style={compactPanelStyle}>
            <Statistic title="检测记录" value={stats.runs} />
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div style={compactPanelStyle}>
            <Statistic title="回答样本" value={stats.samples} />
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div style={compactPanelStyle}>
            <Statistic title="已完成" value={stats.completed} />
          </div>
        </Col>
        <Col xs={12} lg={6}>
          <div style={compactPanelStyle}>
            <Statistic title="检测平台" value={stats.targets} />
          </div>
        </Col>
      </Row>
      <div style={panelStyle}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text strong>信源资产分析</Text>
            <div>
              <Text type="secondary">分析 AI 回答引用的是你的自有资产、权威来源、搜索中转页还是第三方页面。</Text>
            </div>
          </div>
          <Button icon={<ReloadOutlined />} loading={sourceAnalysisLoading} onClick={() => loadSourceAnalysis(selectedProjectId)}>
            刷新分析
          </Button>
        </Space>
        <Spin spinning={sourceAnalysisLoading}>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} lg={6}>
              <div style={compactPanelStyle}>
                <Statistic title="来源覆盖率" value={sourceAnalysis?.source_coverage_rate || 0} suffix="%" />
              </div>
            </Col>
            <Col xs={12} lg={6}>
              <div style={compactPanelStyle}>
                <Statistic title="来源总数" value={sourceAnalysis?.total_sources || 0} />
              </div>
            </Col>
            <Col xs={12} lg={6}>
              <div style={compactPanelStyle}>
                <Statistic title="自有信源占比" value={sourceAnalysis?.owned_asset_rate || 0} suffix="%" />
              </div>
            </Col>
            <Col xs={12} lg={6}>
              <div style={compactPanelStyle}>
                <Statistic title="已配置信源资产" value={sourceAnalysis?.source_assets_configured || 0} />
              </div>
            </Col>
          </Row>
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <div style={compactPanelStyle}>
                <Text strong>来源类型</Text>
                <div style={{ marginTop: 10 }}>
                  {(sourceAnalysis?.category_counts || []).length ? (
                    <Space wrap>
                      {sourceAnalysis.category_counts.map((item) => (
                        <Tag key={item.category} color={sourceCategoryColor(item.category)}>
                          {item.label} {item.count}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">暂无来源类型数据</Text>
                  )}
                </div>
              </div>
            </Col>
            <Col xs={24} lg={12}>
              <div style={compactPanelStyle}>
                <Text strong>优化提示</Text>
                <ul style={{ margin: '10px 0 0', paddingLeft: 20 }}>
                  {(sourceAnalysis?.suggestions || ['暂无来源数据，完成检测后再分析。']).map((item) => (
                    <li key={item}><Text>{item}</Text></li>
                  ))}
                </ul>
              </div>
            </Col>
            <Col span={24}>
              <div style={compactPanelStyle}>
                <Text strong>高频来源域名</Text>
                <div style={{ marginTop: 10 }}>
                  {(sourceAnalysis?.top_domains || []).length ? (
                    <Space wrap>
                      {sourceAnalysis.top_domains.map((item) => (
                        <Tag key={item.domain} color={sourceCategoryColor(item.category)}>
                          {item.domain} · {item.category_label} · {item.count}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">暂无高频来源域名</Text>
                  )}
                </div>
              </div>
            </Col>
          </Row>
        </Spin>
      </div>
      <div style={panelStyle}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text strong>平台推荐表现与趋势</Text>
            <div>
              <Text type="secondary">按实际回答样本聚合，快速判断哪个 AI 平台更愿意提及、推荐品牌，以及近期趋势是否变好。</Text>
            </div>
          </div>
        </Space>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <div style={compactPanelStyle}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text strong>平台推荐率对比</Text>
                <Tag color={platformPerformance.length ? 'blue' : 'default'}>
                  {platformPerformance.length ? `${platformPerformance.length} 个平台` : '暂无数据'}
                </Tag>
              </Space>
              {platformPerformance.length ? (
                <List
                  dataSource={platformPerformance}
                  renderItem={(item, index) => (
                    <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                      <div style={{ width: '100%' }}>
                        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Space wrap>
                            <Text strong>{index + 1}. {item.platform}</Text>
                            <Tag>样本 {item.sample_count}</Tag>
                            <Tag color="green">推荐 {item.recommended_count}</Tag>
                            <Tag color="blue">提及 {item.mentioned_count}</Tag>
                          </Space>
                          <Text type="secondary">推荐率 {item.recommendation_rate}%</Text>
                        </Space>
                        <Progress
                          percent={item.recommendation_rate}
                          size="small"
                          strokeColor={item.recommendation_rate >= 30 ? '#52c41a' : '#1677ff'}
                        />
                        <Space wrap size={12}>
                          <Text type="secondary">提及率 {item.mention_rate}%</Text>
                          <Text type="secondary">来源覆盖 {item.source_coverage_rate}%</Text>
                          <Text type="secondary">自有信源样本 {item.owned_source_samples}</Text>
                        </Space>
                      </div>
                    </List.Item>
                  )}
                />
              ) : (
                <Text type="secondary">完成自动检测后，会在这里展示各平台的推荐率和来源覆盖情况。</Text>
              )}
            </div>
          </Col>
          <Col xs={24} lg={12}>
            <div style={compactPanelStyle}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text strong>近 14 天检测趋势</Text>
                <Tag color={trendRows.length ? 'purple' : 'default'}>
                  {trendRows.length ? `${trendRows.length} 天` : '暂无数据'}
                </Tag>
              </Space>
              {trendRows.length ? (
                <List
                  dataSource={trendRows}
                  renderItem={(item) => (
                    <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                      <div style={{ width: '100%' }}>
                        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Space wrap>
                            <Text strong>{item.label}</Text>
                            <Tag>样本 {item.sample_count}</Tag>
                            <Tag color="green">推荐 {item.recommended_count}</Tag>
                            <Tag color="blue">提及 {item.mentioned_count}</Tag>
                          </Space>
                          <Text type="secondary">推荐率 {item.recommendation_rate}%</Text>
                        </Space>
                        <Progress
                          percent={item.recommendation_rate}
                          size="small"
                          strokeColor={item.recommendation_rate >= 30 ? '#52c41a' : '#faad14'}
                        />
                        <Space wrap size={12}>
                          <Text type="secondary">提及率 {item.mention_rate}%</Text>
                          <Text type="secondary">来源覆盖 {item.source_coverage_rate}%</Text>
                        </Space>
                      </div>
                    </List.Item>
                  )}
                />
              ) : (
                <Text type="secondary">暂无可计算趋势的检测样本。</Text>
              )}
            </div>
          </Col>
        </Row>
      </div>
      <div style={panelStyle}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text strong>检测明细（问题 × 平台）</Text>
            <div>
              <Text type="secondary">每一行是一道问题在一个 AI 平台上的实际回答，可查看原文和信息来源。</Text>
            </div>
          </div>
          <Button icon={<ReloadOutlined />} onClick={() => loadSamples(selectedProjectId)}>
            刷新明细
          </Button>
        </Space>
        <Table
          rowKey="id"
          columns={sampleColumns}
          dataSource={filteredSamples}
          loading={sampleLoading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1720 }}
          locale={{ emptyText: '暂无检测明细，完成自动检测后会出现在这里' }}
        />
      </div>
      <div style={panelStyle}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text strong>检测记录</Text>
            <div>
              <Text type="secondary">这里保留每次自动检测的结果，可以查看指标、生成建议、设为基线或删除。</Text>
            </div>
          </div>
          <Button icon={<ReloadOutlined />} onClick={loadRuns}>
            刷新
          </Button>
        </Space>
        <Table
          rowKey="id"
          columns={runColumns}
          dataSource={filteredRuns}
          pagination={{ pageSize: 8 }}
          locale={{ emptyText: '暂无检测记录' }}
        />
      </div>
    </div>
  );

  const renderTargetsTab = () => (
    <div>
      <div style={panelStyle}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text strong>检测平台</Text>
            <div>
              <Text type="secondary">配置要打开的 AI 网页。系统会自动识别 Kimi WebBridge 或 QWebBridge，打开网页提问并读取回答。</Text>
            </div>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openTargetModal()}>
            添加平台
          </Button>
        </Space>
        <Table
          rowKey="id"
          columns={targetColumns}
          dataSource={modelTargets}
          pagination={{ pageSize: 8 }}
          locale={{ emptyText: '暂无检测平台' }}
        />
      </div>
    </div>
  );

  const renderAdvancedTab = () => (
    <div style={panelStyle}>
      <Title level={4}>高级分析</Title>
      <Paragraph type="secondary">
        主流程已经把“自动提问、采样、指标计算、建议生成”串起来了。这里保留高级能力的解释，避免把日常检测流程做复杂。
      </Paragraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <div style={compactPanelStyle}>
            <Text strong>基线对比</Text>
            <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              在检测记录里点击“设为基线”，后续就能用它作为同平台、同问题的对照样本。
            </Paragraph>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div style={compactPanelStyle}>
            <Text strong>优化建议</Text>
            <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              “建议”会根据品牌提及率、推荐率、引用线索和负面反馈生成下一轮内容补强方向。
            </Paragraph>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div style={compactPanelStyle}>
            <Text strong>原始样本</Text>
            <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              自动检测会把网页回答写入样本库，后续报告中心可以继续汇总使用。
            </Paragraph>
          </div>
        </Col>
      </Row>
    </div>
  );

  const renderProjectOverview = () => (
    <div style={panelStyle}>
      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={8}>
          <Space direction="vertical" size={4}>
            <Text type="secondary">当前监测项目</Text>
            <Title level={4} style={{ margin: 0 }}>{selectedProject?.name || '未选择项目'}</Title>
            <Space wrap>
              <Tag color="blue">{selectedProject?.industry || '未填写行业'}</Tag>
              <Tag color="green">{selectedProject?.region || '未填写地区'}</Tag>
              <Tag color={selectedProject?.status === 'active' ? 'processing' : 'default'}>
                {selectedProject?.status || 'unknown'}
              </Tag>
            </Space>
          </Space>
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="启用问题" value={stats.questions} suffix="个" />
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="检测平台" value={stats.targets} suffix="个" />
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="检测样本" value={stats.samples} suffix="条" />
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="检测记录" value={stats.runs} suffix="次" />
        </Col>
        <Col span={24}>
          <Space wrap size={12}>
            <Text type="secondary">目标 AI 产品：{selectedProject?.target_ai_products || '未填写'}</Text>
            <Text type="secondary">最近检测：{stats.latestSampleAt ? formatTime(stats.latestSampleAt) : '暂无样本'}</Text>
          </Space>
        </Col>
      </Row>
    </div>
  );

  const readableReport = buildReadableReport(reportData);

  return (
    <div>
      <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>监测分析</Title>
          <Text type="secondary">
            选择项目、平台和问题后，一键完成自动检测，并沉淀可追踪的 GEO 检测结果。
          </Text>
        </div>
        <Select
          value={selectedProjectId}
          onChange={setSelectedProjectId}
          style={{ width: 320 }}
          placeholder="选择项目"
          options={projects.map((item) => ({ label: item.name, value: item.id }))}
        />
      </Space>

      <Spin spinning={loading}>
        {renderProjectOverview()}
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'start',
              label: (
                <Space>
                  <ThunderboltOutlined />
                  开始检测
                </Space>
              ),
              children: renderStartTab(),
            },
            {
              key: 'records',
              label: (
                <Space>
                  <BarChartOutlined />
                  检测记录
                  <Badge count={stats.runs} size="small" />
                </Space>
              ),
              children: renderRecordsTab(),
            },
            {
              key: 'targets',
              label: (
                <Space>
                  <SettingOutlined />
                  检测平台
                  <Badge count={stats.targets} size="small" color="#1677ff" />
                </Space>
              ),
              children: renderTargetsTab(),
            },
            {
              key: 'advanced',
              label: '高级分析',
              children: renderAdvancedTab(),
            },
          ]}
        />
      </Spin>

      <Modal
        title={editingTarget ? '编辑检测平台' : '添加检测平台'}
        open={targetModalVisible}
        onCancel={() => {
          setTargetModalVisible(false);
          setEditingTarget(null);
        }}
        onOk={() => targetForm.submit()}
        okText={editingTarget ? '保存' : '添加'}
        cancelText="取消"
        destroyOnClose
        width={720}
      >
        <Form form={targetForm} layout="vertical" onFinish={handleSubmitTarget}>
          <Form.Item name="project_id" label="所属项目" rules={[{ required: true, message: '请选择项目' }]}>
            <Select
              options={projects.map((item) => ({ label: item.name, value: item.id }))}
              onChange={setSelectedProjectId}
            />
          </Form.Item>
          <Form.Item name="product_name" label="平台名称" rules={[{ required: true, message: '请输入平台名称' }]}>
            <Input placeholder="例如：Kimi、豆包、DeepSeek" />
          </Form.Item>
          <Form.Item name="web_url" label="网页地址" rules={[{ required: true, message: '请输入网页地址' }]}>
            <Input placeholder="例如：https://www.doubao.com/chat/" />
          </Form.Item>
          <Form.Item name="supported_mechanisms" label="检测机制">
            <Checkbox.Group
              options={[
                { label: '推荐/问答', value: 'B' },
                { label: '搜索摘要', value: 'A' },
                { label: '引用来源', value: 'C' },
              ]}
            />
          </Form.Item>
          <Form.Item name="access_method" label="调用方式">
            <Select
              options={[
                { label: 'WebBridge 自动网页', value: 'webbridge' },
                { label: '手动记录', value: 'manual' },
              ]}
            />
          </Form.Item>
          <Form.Item name="recognition_mode" label="识别模式">
            <Select
              options={[
                { label: '文本抓取模式（默认，使用 DOM/选择器读取回答）', value: 'text' },
                { label: '视觉识别模式（截图 + 多模态模型识别）', value: 'vision' },
              ]}
            />
          </Form.Item>
          {targetRecognitionMode === 'vision' ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="已开启视觉识别模式：本平台检测时会关闭文本抓取识别，只通过截图和多模态模型定位输入、发送和读取回答。"
              description="请先在 AI 模型里配置支持图片理解的模型。该模式适合 DOM 结构复杂、发送按钮或回答区域难以用选择器稳定抓取的网页。"
            />
          ) : (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="当前为默认文本抓取模式：优先使用页面文本、DOM 和可选 selector 读取回答，成本更低、速度更快。"
            />
          )}
          <Divider orientation="left">高级选择器</Divider>
          <Alert
            type={targetRecognitionMode === 'vision' ? 'warning' : 'info'}
            showIcon
            style={{ marginBottom: 16 }}
            message={targetRecognitionMode === 'vision'
              ? '视觉识别模式下 selector 不参与识别，以下字段仅保留用于切回文本抓取模式。'
              : '网页自动提问点不到发送按钮时，把错误日志里的候选 selector 填到 submit_selector。'}
          />
          <Form.Item name="input_selector" label="input_selector（输入框，可选）">
            <Input disabled={targetRecognitionMode === 'vision'} placeholder="例如：textarea 或 [contenteditable='true']，留空则自动识别" />
          </Form.Item>
          <Form.Item name="submit_selector" label="submit_selector（发送按钮，可选）">
            <Input disabled={targetRecognitionMode === 'vision'} placeholder="例如：button[aria-label='发送']，点不到发送时填写" />
          </Form.Item>
          <Form.Item name="response_selector" label="response_selector（回答区域，可选）">
            <Input disabled={targetRecognitionMode === 'vision'} placeholder="例如：.answer-list，留空则读取页面正文尾部" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <TextArea rows={3} placeholder="可记录登录要求、页面注意事项等" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="检测结果"
        open={reportModalVisible}
        onCancel={() => setReportModalVisible(false)}
        footer={<Button onClick={() => setReportModalVisible(false)}>关闭</Button>}
        width={860}
      >
        <Spin spinning={reportLoading}>
          {reportData && readableReport ? (
            <Space direction="vertical" style={{ width: '100%' }} size={16}>
              <Alert
                type={readableReport.alertType}
                showIcon
                message={readableReport.conclusion}
                description={
                  <Space direction="vertical" size={2}>
                    <Text>
                      本次检测了 {readableReport.sampleCount} 个问题，置信等级：
                      <Tag color={readableReport.confidence.color} style={{ marginLeft: 6 }}>
                        {readableReport.confidence.label}
                      </Tag>
                      {readableReport.confidence.hint}
                    </Text>
                    {selectedRun && <Text type="secondary">检测记录：{selectedRun.id}</Text>}
                  </Space>
                }
              />

              <Row gutter={[16, 16]}>
                {readableReport.rows.map((item) => (
                  <Col xs={24} md={12} key={item.label}>
                    <div style={compactPanelStyle}>
                      <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
                        <div>
                          <Text strong>{item.label}</Text>
                          <div style={{ marginTop: 4 }}>
                            <Text type="secondary">{item.value} 个样本</Text>
                          </div>
                        </div>
                        <Statistic value={item.percent} />
                      </Space>
                      <Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0 }}>
                        {item.explain}
                      </Paragraph>
                    </div>
                  </Col>
                ))}
              </Row>

              <div style={compactPanelStyle}>
                <Text strong>下一步建议</Text>
                <ul style={{ margin: '10px 0 0', paddingLeft: 20 }}>
                  {readableReport.suggestions.map((item) => (
                    <li key={item} style={{ marginBottom: 6 }}>
                      <Text>{item}</Text>
                    </li>
                  ))}
                </ul>
              </div>

              <details>
                <summary style={{ cursor: 'pointer', color: '#1677ff' }}>查看原始 JSON（调试用）</summary>
                <pre style={{ background: '#f7f8fa', padding: 16, borderRadius: 8, maxHeight: 320, overflow: 'auto', marginTop: 12 }}>
                  {JSON.stringify(reportData, null, 2)}
                </pre>
              </details>
            </Space>
          ) : (
            <Text type="secondary">暂无结果</Text>
          )}
        </Spin>
      </Modal>

      <Modal
        title="AI 搜索详情"
        open={!!sampleDetail}
        onCancel={() => setSampleDetail(null)}
        footer={(
          <Space>
            <Button onClick={() => setSampleDetail(null)}>关闭</Button>
            {sampleDetail && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                loading={savingReviewSampleId === sampleDetail.id}
                onClick={() => handleSaveSampleReviewKnowledge(sampleDetail)}
              >
                沉淀为复盘资料
              </Button>
            )}
          </Space>
        )}
        width={920}
      >
        {sampleDetail && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Alert
              type={sampleDetail.recommended ? 'success' : sampleDetail.brand_mentioned ? 'warning' : 'info'}
              showIcon
              message={`${sampleDetail.model_target_name || 'AI平台'}：${sampleDetail.recommended ? '已推荐' : sampleDetail.brand_mentioned ? '已提及但未明确推荐' : '未提及品牌'}`}
              description={`检测时间：${formatTime(sampleDetail.sampled_at)}`}
            />
            <div style={compactPanelStyle}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text strong>AI 判断依据</Text>
                <Space wrap>
                  <Tag color={sampleDetail.analysis?.sentiment === 'negative' ? 'red' : sampleDetail.analysis?.sentiment === 'positive' ? 'green' : 'blue'}>
                    {sampleDetail.analysis?.sentiment_label || '未生成情绪判断'}
                  </Tag>
                  {sampleDetail.analysis?.review_required && <Tag color="orange">建议人工复核</Tag>}
                </Space>
              </Space>
              <Space wrap style={{ marginBottom: 8 }}>
                {(sampleDetail.analysis?.matched_brand_terms || []).map((item) => (
                  <Tag key={`brand-${item}`} color="blue">品牌词：{item}</Tag>
                ))}
                {(sampleDetail.analysis?.recommendation_keywords || []).map((item) => (
                  <Tag key={`recommend-${item}`} color="green">推荐词：{item}</Tag>
                ))}
                {(sampleDetail.analysis?.negative_keywords || []).map((item) => (
                  <Tag key={`negative-${item}`} color="red">风险词：{item}</Tag>
                ))}
              </Space>
              {(sampleDetail.analysis?.judgment_basis || []).length ? (
                <List
                  size="small"
                  dataSource={sampleDetail.analysis.judgment_basis}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              ) : (
                <Text type="secondary">历史样本暂无判断依据，新检测样本会自动记录。</Text>
              )}
            </div>
            <div style={compactPanelStyle}>
              <Text strong>问题</Text>
              <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{sampleDetail.question_text || '-'}</Paragraph>
            </div>
            {sampleDetail.analysis?.mention_evidence?.evidence_text && (
              <div style={compactPanelStyle}>
                <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text strong>品牌提及证据</Text>
                  <Space wrap>
                    {sampleDetail.analysis.mention_evidence.matched_term && (
                      <Tag color="red">命中：{sampleDetail.analysis.mention_evidence.matched_term}</Tag>
                    )}
                    <Tag color={sampleDetail.analysis.mention_evidence.source === 'page_dom' ? 'green' : 'blue'}>
                      {sampleDetail.analysis.mention_evidence.source === 'page_dom' ? '页面定位' : '文本定位'}
                    </Tag>
                  </Space>
                </Space>
                <pre style={{ whiteSpace: 'pre-wrap', background: '#fff7f7', padding: 12, borderRadius: 6, maxHeight: 220, overflow: 'auto', marginTop: 8, border: '1px solid #ffccc7' }}>
                  {sampleDetail.analysis.mention_evidence.evidence_text}
                </pre>
              </div>
            )}
            <div style={compactPanelStyle}>
              <Text strong>AI 原始回答</Text>
              <pre style={{ whiteSpace: 'pre-wrap', background: '#f7f8fa', padding: 12, borderRadius: 6, maxHeight: 320, overflow: 'auto', marginTop: 8 }}>
                {sampleDetail.answer_text || '暂无回答文本'}
              </pre>
            </div>
            <div style={compactPanelStyle}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text strong>{sampleDetail.analysis?.mention_evidence?.screenshot_url ? '品牌提及位置截图' : '回答截图'}</Text>
                <Tag color={sampleDetail.screenshot_url ? 'green' : 'default'}>
                  {sampleDetail.screenshot_url ? '已保存截图' : '暂无截图'}
                </Tag>
              </Space>
              {sampleDetail.screenshot_url ? (
                <img
                  src={apiAssetUrl(sampleDetail.screenshot_url)}
                  alt="AI回答截图"
                  style={{ width: '100%', maxHeight: 420, objectFit: 'contain', border: '1px solid #f0f0f0', borderRadius: 6, background: '#fafafa' }}
                />
              ) : (
                <Text type="secondary">历史样本或当前浏览器桥接未返回截图时，这里不会展示图片。</Text>
              )}
            </div>
            <div style={compactPanelStyle}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text strong>信息来源（{sampleDetail.sources?.length || 0} 条）</Text>
                <Tag color={(sampleDetail.sources?.length || 0) > 0 ? 'blue' : 'default'}>
                  {(sampleDetail.sources?.length || 0) > 0 ? '已抓取来源' : '未发现来源链接'}
                </Tag>
              </Space>
              {(sampleDetail.sources?.length || 0) > 0 ? (
                <List
                  size="small"
                  dataSource={sampleDetail.sources || []}
                  renderItem={(item, index) => (
                    <List.Item>
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        <a href={item.url} target="_blank" rel="noreferrer">
                          <LinkOutlined /> {item.title || item.url || `来源 ${index + 1}`}
                        </a>
                        <Space size={4} wrap>
                          <Tag color={sourceCategoryColor(item.category)}>{item.category_label || '未知来源'}</Tag>
                          {item.is_own_asset && <Tag color="green">已匹配自有信源</Tag>}
                          {item.domain && <Tag>{item.domain}</Tag>}
                        </Space>
                        <Text type="secondary" copyable={{ text: item.url }}>{item.url}</Text>
                        {item.context && <Text type="secondary">{item.context}</Text>}
                      </Space>
                    </List.Item>
                  )}
                />
              ) : (
                <Text type="secondary">当前 AI 回答区域没有可识别的来源链接。部分平台不会为普通回答展示引用来源。</Text>
              )}
            </div>
          </Space>
        )}
      </Modal>
    </div>
  );
}

export default Monitoring;
