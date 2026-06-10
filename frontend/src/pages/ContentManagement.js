import React, { useState, useEffect } from 'react';
import {
  Button, Tag, Tabs, Modal, Form, Input, Select, Radio,
  message, Spin, Space, Typography, Badge, Divider, Alert,
  List, Empty,
} from 'antd';
import {
  PlusOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  RobotOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  WarningOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import {
  contentTasksApi,
  contentDraftsApi,
  projectsApi,
  corpusItemsApi,
  writingMemoryApi,
  questionsApi,
  channelAccountsApi,
  publishRecordsApi,
} from '../services/api';
import Table from '../components/SafeTable';

const { Option, OptGroup } = Select;
const { TextArea } = Input;
const { Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const statusColors = {
  draft: 'default',
  in_progress: 'processing',
  review: 'warning',
  approved: 'success',
  client_review: 'blue',
  publish_ready: 'cyan',
  published: 'green',
  completed: 'success',
  blocked: 'error',
};

const statusLabels = {
  draft: '草稿',
  in_progress: '进行中',
  review: '待审核',
  approved: '已通过',
  client_review: '客户复核',
  publish_ready: '待发布',
  published: '已发布',
  completed: '已完成',
  blocked: '已阻塞',
};

const layerLabels = {
  verification_layer: '基础验证层',
  pool_layer: '入池层',
  weight_layer: '权重提升层',
  conversion_layer: '转化承接层',
};

const platformLabels = {
  media: '媒体稿',
  official_account: '公众号',
  shipinhao: '视频号',
  xiaohongshu: '小红书',
  b2b_product: 'B2B产品页',
  official_faq: '官网FAQ',
  website: '官网',
  baijiahao: '百家号',
  zhihu: '知乎',
  toutiao: '头条',
  netease: '网易号',
  sina: '新浪看点',
  penguin: '企鹅号',
  other: '其他',
};

const layerPlatformRecommendations = {
  verification_layer: ['website', 'official_faq', 'baijiahao', 'zhihu'],
  pool_layer: ['baijiahao', 'toutiao', 'media'],
  weight_layer: ['zhihu', 'baijiahao', 'toutiao'],
  conversion_layer: ['official_account', 'website', 'xiaohongshu'],
};

const contentTypePlatformRecommendations = {
  faq: ['official_faq', 'website', 'baijiahao'],
  product: ['website', 'b2b_product', 'baijiahao'],
  case_study: ['media', 'baijiahao', 'official_account'],
  pr: ['media', 'toutiao', 'netease', 'sina'],
  recommendation: ['zhihu', 'baijiahao', 'toutiao'],
  brand_intro: ['media', 'official_account', 'baijiahao'],
};

const getRecommendedPlatformsForTask = (task = {}) => {
  const ordered = [
    ...(contentTypePlatformRecommendations[task.content_type] || []),
    ...(layerPlatformRecommendations[task.layer] || []),
    'media',
  ];
  const seen = new Set();
  return ordered.filter((platform) => {
    if (!platform || seen.has(platform)) return false;
    seen.add(platform);
    return true;
  }).slice(0, 4);
};

const formatApiDetail = (detail) => {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(formatApiDetail).filter(Boolean).join('；');
  }
  if (typeof detail === 'object') {
    const messageText = detail.message || detail.msg || detail.detail || '';
    const issueText = Array.isArray(detail.issues)
      ? detail.issues
        .slice(0, 5)
        .map((item) => item?.message || item?.name || formatApiDetail(item))
        .filter(Boolean)
        .join('；')
      : '';
    return [messageText, issueText].filter(Boolean).join('：') || JSON.stringify(detail);
  }
  return String(detail);
};

const formatApiError = (error) => (
  formatApiDetail(error.response?.data?.detail)
  || formatApiDetail(error.response?.data)
  || error.message
  || '未知错误'
);

const getForceSavePublishDetail = (error) => {
  const detail = error.response?.data?.detail;
  return detail && typeof detail === 'object' && detail.can_force_save ? detail : null;
};

const normalizeKey = (value) => String(value || '').trim().toLowerCase();

const parsePublishTargetValue = (value, channelAccounts) => {
  const raw = String(value || '').trim();
  if (!raw) return null;
  if (raw.startsWith('account:')) {
    const accountId = raw.slice('account:'.length);
    const account = channelAccounts.find((item) => item.id === accountId);
    if (!account) return null;
    return {
      key: `account:${account.id}`,
      channel_account_id: account.id,
      platform: account.platform || 'other',
      account_name: account.account_name,
      label: `${platformLabels[account.platform] || account.platform || '其他'} / ${account.account_name}`,
    };
  }
  const platform = raw.startsWith('platform:') ? raw.slice('platform:'.length) : raw;
  return {
    key: `platform:${platform}`,
    channel_account_id: undefined,
    platform,
    account_name: undefined,
    label: platformLabels[platform] || platform,
  };
};

const buildPublishTargets = (values = [], channelAccounts = []) => {
  const seen = new Set();
  return values
    .map((value) => parsePublishTargetValue(value, channelAccounts))
    .filter(Boolean)
    .filter((target) => {
      if (seen.has(target.key)) return false;
      seen.add(target.key);
      return true;
    });
};

const parsePublishUrls = (text = '', targets = []) => {
  const lines = String(text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const keyed = {};
  const bare = [];
  lines.forEach((line) => {
    const match = line.match(/^(.+?)[=：:]\s*(https?:\/\/.+)$/i);
    if (match) {
      keyed[normalizeKey(match[1])] = match[2].trim();
    } else if (/^https?:\/\//i.test(line)) {
      bare.push(line);
    }
  });
  return targets.map((target, index) => {
    const candidates = [
      target.platform,
      platformLabels[target.platform],
      target.account_name,
      target.label,
    ].map(normalizeKey);
    const matchedUrl = candidates.map((key) => keyed[key]).find(Boolean);
    return {
      ...target,
      url: matchedUrl || (targets.length === 1 ? bare[0] : bare[index]),
    };
  });
};

const formatTaskDueDate = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

function ContentManagement() {
  const [tasks, setTasks] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [projects, setProjects] = useState([]);
  const [questionGroups, setQuestionGroups] = useState([]);
  const [knowledgeAssets, setKnowledgeAssets] = useState([]);
  const [knowledgeAssetsLoading, setKnowledgeAssetsLoading] = useState(false);
  const [channelAccounts, setChannelAccounts] = useState([]);
  const [publishRecords, setPublishRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('1');

  // 任务Modal
  const [taskModalVisible, setTaskModalVisible] = useState(false);
  const [taskForm] = Form.useForm();

  // 草稿生成Modal
  const [generateModalVisible, setGenerateModalVisible] = useState(false);
  const [generateForm] = Form.useForm();
  const [generatingTask, setGeneratingTask] = useState(null);
  const [generating, setGenerating] = useState(false);

  // 草稿详情/编辑Modal
  const [draftModalVisible, setDraftModalVisible] = useState(false);
  const [viewingDraft, setViewingDraft] = useState(null);
  const [draftForm] = Form.useForm();
  const [feedbackForm] = Form.useForm();

  // 合规检查Modal
  const [validationResult, setValidationResult] = useState(null);
  const [validationModalVisible, setValidationModalVisible] = useState(false);

  // 草稿反馈/记忆写入
  const [draftFeedbacks, setDraftFeedbacks] = useState([]);
  const [lastAppliedFeedback, setLastAppliedFeedback] = useState(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);

  // 发布渠道/发布记录
  const [channelModalVisible, setChannelModalVisible] = useState(false);
  const [channelForm] = Form.useForm();
  const [publishModalVisible, setPublishModalVisible] = useState(false);
  const [publishForm] = Form.useForm();
  const [publishingDraft, setPublishingDraft] = useState(null);
  const [publishAssistVisible, setPublishAssistVisible] = useState(false);
  const [publishAssistLoading, setPublishAssistLoading] = useState(false);
  const [publishAssistResult, setPublishAssistResult] = useState(null);

  const loadProjects = async () => {
    try {
      const res = await projectsApi.list({ limit: 100 });
      const items = res.data || [];
      setProjects(items);
    } catch (error) {
      message.error('加载项目失败');
    }
  };

  const loadTasks = async () => {
    setLoading(true);
    try {
      const res = await contentTasksApi.list({ limit: 100 });
      setTasks(res.data || []);
    } catch (error) {
      message.error('加载内容任务失败');
    } finally {
      setLoading(false);
    }
  };

  const loadDrafts = async () => {
    setLoading(true);
    try {
      const res = await contentDraftsApi.list({ limit: 100 });
      setDrafts(res.data || []);
    } catch (error) {
      message.error('加载草稿失败');
    } finally {
      setLoading(false);
    }
  };

  const loadQuestionGroups = async (projectId) => {
    if (!projectId) {
      setQuestionGroups([]);
      return;
    }
    try {
      const res = await questionsApi.listGroups({ project_id: projectId });
      setQuestionGroups(res.data || []);
    } catch (error) {
      setQuestionGroups([]);
      message.error('加载问题矩阵失败');
    }
  };

  const loadKnowledgeAssets = async (projectId) => {
    if (!projectId) {
      setKnowledgeAssets([]);
      return;
    }
    setKnowledgeAssetsLoading(true);
    try {
      const res = await corpusItemsApi.list({ project_id: projectId, limit: 200 });
      setKnowledgeAssets(res.data || []);
    } catch (error) {
      setKnowledgeAssets([]);
      message.error('加载项目知识资产失败');
    } finally {
      setKnowledgeAssetsLoading(false);
    }
  };

  const loadChannelAccounts = async () => {
    try {
      const res = await channelAccountsApi.list({ limit: 100 });
      setChannelAccounts(res.data || []);
    } catch (error) {
      message.error('加载发布渠道失败');
    }
  };

  const loadPublishRecords = async () => {
    setLoading(true);
    try {
      const res = await publishRecordsApi.list({ limit: 100 });
      setPublishRecords(res.data || []);
    } catch (error) {
      message.error('加载发布记录失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    loadTasks();
    loadDrafts();
    loadChannelAccounts();
    loadPublishRecords();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateTask = async (values) => {
    if (!values.project_id) {
      message.warning('请先选择内容任务所属项目');
      return;
    }
    const payload = { ...values };
    delete payload.question_link;
    delete payload.group_id;
    delete payload.question_id;
    if (values.question_link) {
      const [linkType, linkId] = String(values.question_link).split(':');
      if (linkType === 'question') {
        const group = questionGroups.find((item) =>
          (item.questions || []).some((question) => question.id === linkId)
        );
        payload.question_id = linkId;
        payload.group_id = group?.id;
      } else if (linkType === 'group') {
        payload.group_id = linkId;
      }
    }
    try {
      await contentTasksApi.create(payload);
      message.success('内容任务已创建');
      setTaskModalVisible(false);
      taskForm.resetFields();
      loadTasks();
    } catch (error) {
      message.error('创建失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openCreateTaskModal = () => {
    const defaultProjectId = projects[0]?.id;
    taskForm.setFieldsValue({
      project_id: defaultProjectId,
      group_id: undefined,
      question_id: undefined,
      question_link: undefined,
      knowledge_asset_ids: [],
      content_type: 'brand_intro',
      layer: 'verification_layer',
      priority: 'medium',
    });
    loadQuestionGroups(defaultProjectId);
    loadKnowledgeAssets(defaultProjectId);
    setTaskModalVisible(true);
  };

  const openGenerateModal = (task) => {
    const projectExists = task.project_id && projects.some((project) => project.id === task.project_id);
    if (!projectExists) {
      message.error('该内容任务没有绑定有效项目，请删除后重新创建，并选择真实项目');
      return;
    }
    setGeneratingTask(task);
    const recommendedPlatforms = getRecommendedPlatformsForTask(task);
    generateForm.setFieldsValue({
      content_type: task.content_type || 'brand_intro',
      platforms: recommendedPlatforms,
    });
    setGenerateModalVisible(true);
  };

  const handleGenerate = async (values) => {
    if (!generatingTask) return;
    setGenerating(true);
    try {
      const platforms = Array.isArray(values.platforms) && values.platforms.length
        ? values.platforms
        : [values.platform || 'media'];
      const results = [];
      const failures = [];
      for (const platform of platforms) {
        try {
          const res = await contentDraftsApi.generate(generatingTask.id, {
            ...values,
            platform,
          });
          results.push({ platform, data: res.data });
        } catch (error) {
          const detail = error.code === 'ECONNABORTED'
            ? '生成时间过长'
            : formatApiError(error);
          failures.push({ platform, detail });
        }
      }
      if (results.length > 0) {
        message.success(platforms.length > 1 ? `已生成 ${results.length} 个平台草稿` : '草稿生成成功');
        setGenerateModalVisible(false);
        generateForm.resetFields();
        setGeneratingTask(null);
        loadDrafts();
        setActiveTab('2');
      }
      if (failures.length > 0) {
        const failureText = failures
          .map((item) => `${platformLabels[item.platform] || item.platform}: ${item.detail}`)
          .join('；');
        if (results.length > 0) {
          message.warning(`部分平台生成失败：${failureText}`);
        } else {
          message.error(`生成失败：${failureText}`);
        }
      }

      // 如果有合规问题，提示
      const issueCount = results.reduce(
        (sum, item) => sum + (item?.data?.compliance_issues?.length || 0),
        0,
      );
      if (issueCount > 0) {
        message.warning(`生成完成，但发现 ${issueCount} 个合规问题，请检查`);
      }
    } catch (error) {
      const detail = error.code === 'ECONNABORTED'
        ? '生成时间过长，请稍后重试；如果模型响应较慢，可以减少文章长度或换响应更快的模型。'
        : formatApiError(error);
      message.error('生成失败: ' + detail);
    } finally {
      setGenerating(false);
    }
  };

  const openDraftModal = (draft) => {
    setViewingDraft(draft);
    setLastAppliedFeedback(null);
    draftForm.setFieldsValue({
      title: draft.title,
      body: draft.body,
      platform: draft.platform || 'media',
      status: draft.status,
      risk_level: draft.risk_level,
    });
    feedbackForm.resetFields();
    loadDraftFeedbacks(draft);
    setDraftModalVisible(true);
  };

  const handleUpdateDraft = async (values) => {
    if (!viewingDraft) return;
    try {
      await contentDraftsApi.update(viewingDraft.id, values);
      message.success('草稿已更新');
      setDraftModalVisible(false);
      loadDrafts();
    } catch (error) {
      message.error('更新失败');
    }
  };

  const handleValidatePublishReady = async (draft) => {
    try {
      const res = await contentDraftsApi.validatePublishReady(draft.id);
      setValidationResult(res.data);
      setValidationModalVisible(true);
    } catch (error) {
      message.error('验证失败');
    }
  };

  const handleDeleteTask = async (id) => {
    try {
      await contentTasksApi.delete(id);
      message.success('任务已删除');
      loadTasks();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleDeleteDraft = (draft) => {
    Modal.confirm({
      title: '确认删除这篇文章？',
      content: `删除后无法在列表中恢复：${draft.title || '未命名草稿'}`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await contentDraftsApi.delete(draft.id);
          message.success('文章已删除');
          if (viewingDraft?.id === draft.id) {
            setDraftModalVisible(false);
            setViewingDraft(null);
            setDraftFeedbacks([]);
            setLastAppliedFeedback(null);
          }
          loadDrafts();
        } catch (error) {
          message.error('删除文章失败: ' + (error.response?.data?.detail || error.message));
        }
      },
    });
  };

  const openCreateChannelModal = () => {
    channelForm.setFieldsValue({
      platform: 'official_account',
      account_name: '',
      account_type: 'owned',
      login_required: true,
      publish_permission: true,
      publisher_url: '',
      title_selector: '',
      body_selector: '',
      risk_level: 'low',
      status: 'normal',
    });
    setChannelModalVisible(true);
  };

  const handleCreateChannelAccount = async (values) => {
    try {
      await channelAccountsApi.create(values);
      message.success('发布渠道已添加');
      setChannelModalVisible(false);
      channelForm.resetFields();
      loadChannelAccounts();
    } catch (error) {
      message.error('添加发布渠道失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDeleteChannelAccount = (account) => {
    Modal.confirm({
      title: '确认删除这个发布渠道？',
      content: `渠道：${platformLabels[account.platform] || account.platform} / ${account.account_name}`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await channelAccountsApi.delete(account.id);
          message.success('发布渠道已删除');
          loadChannelAccounts();
        } catch (error) {
          message.error('删除发布渠道失败: ' + (error.response?.data?.detail || error.message));
        }
      },
    });
  };

  const openPublishModal = (draft) => {
    const task = getDraftTask(draft);
    if (!task) {
      message.warning('无法定位草稿对应的内容任务，请刷新后重试');
      return;
    }
    const draftPlatform = draft.platform || 'official_account';
    const defaultAccount = channelAccounts.find((item) => item.platform === draftPlatform && item.publish_permission && item.status === 'normal')
      || channelAccounts.find((item) => item.publish_permission && item.status === 'normal')
      || channelAccounts[0];
    setPublishingDraft(draft);
    publishForm.setFieldsValue({
      publish_targets: defaultAccount?.id ? [`account:${defaultAccount.id}`] : [`platform:${draftPlatform}`],
      title: draft.title,
      urls_text: '',
      status: 'published',
      is_indexed: false,
    });
    setPublishModalVisible(true);
  };

  const handleWebBridgePublishAssist = async (draft) => {
    const task = getDraftTask(draft);
    if (!task) {
      message.warning('无法定位草稿对应的内容任务，请刷新后重试');
      return;
    }
    const draftPlatform = draft.platform || 'other';
    const defaultAccount = channelAccounts.find((item) => item.platform === draftPlatform && item.publish_permission && item.status === 'normal')
      || channelAccounts.find((item) => item.publish_permission && item.status === 'normal')
      || channelAccounts[0];
    setPublishAssistLoading(true);
    setPublishAssistVisible(true);
    setPublishAssistResult(null);
    try {
      const res = await publishRecordsApi.webbridgeAssist({
        draft_id: draft.id,
        channel_account_id: defaultAccount?.id,
        platform: defaultAccount?.platform || draftPlatform || 'other',
      });
      setPublishAssistResult(res.data);
      if (!res.data.can_publish) {
        message.warning('草稿未通过发布检查，请先处理风险项');
      } else if (res.data.webbridge?.ok) {
        message.success('发布页已打开并尝试预填，请人工核对后发布');
      } else {
        message.warning(res.data.webbridge?.message || '已生成发布包，请手动复制发布');
      }
    } catch (error) {
      message.error('发布助手启动失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setPublishAssistLoading(false);
    }
  };

  const copyPublishPackage = async () => {
    const pack = publishAssistResult?.content_package;
    if (!pack) return;
    try {
      await navigator.clipboard.writeText(`${pack.title}\n\n${pack.body}`);
      message.success('标题和正文已复制');
    } catch (error) {
      message.error('复制失败，请手动选中文本复制');
    }
  };

  const savePublishRecords = async (values, targets, task, forceSave = false) => {
    for (const target of targets) {
      await publishRecordsApi.create({
        task_id: task.id,
        draft_id: publishingDraft.id,
        channel_account_id: target.channel_account_id,
        platform: target.platform,
        url: target.url,
        title: values.title || publishingDraft?.title,
        content_type: task.content_type,
        status: values.status,
        is_indexed: values.is_indexed || false,
        force_save: forceSave,
      });
    }
  };

  const afterPublishRecordsSaved = async (values, targets, forceSaved = false) => {
    if (values.status === 'published' && publishingDraft?.id) {
      await contentDraftsApi.update(publishingDraft.id, { status: 'published' });
    }
    message.success(
      targets.length > 1
        ? `已保存 ${targets.length} 条发布记录${forceSaved ? '（已确认风险）' : ''}`
        : `发布记录已保存${forceSaved ? '（已确认风险）' : ''}`,
    );
    setPublishModalVisible(false);
    setPublishingDraft(null);
    publishForm.resetFields();
    loadPublishRecords();
    loadTasks();
    loadDrafts();
    setActiveTab('5');
  };

  const handleCreatePublishRecord = async (values) => {
    const task = getDraftTask(publishingDraft);
    if (!task) {
      message.warning('无法定位草稿对应的内容任务，请刷新后重试');
      return;
    }
    const targets = parsePublishUrls(
      values.urls_text,
      buildPublishTargets(values.publish_targets, channelAccounts),
    );
    if (targets.length === 0) {
      message.warning('请至少选择一个发布渠道，或直接输入一个平台名称');
      return;
    }
    try {
      await savePublishRecords(values, targets, task, false);
      await afterPublishRecordsSaved(values, targets, false);
    } catch (error) {
      const forceSaveDetail = getForceSavePublishDetail(error);
      if (forceSaveDetail) {
        Modal.confirm({
          title: '草稿未通过发布检查',
          width: 680,
          content: (
            <div>
              <p>这篇文章存在以下风险，但如果你确认内容已经实际发布，可以继续保存发布记录。</p>
              <List
                size="small"
                dataSource={forceSaveDetail.issues || []}
                renderItem={(item) => (
                  <List.Item>
                    <Tag color={item.severity === 'high' ? 'red' : 'orange'}>{item.severity || 'risk'}</Tag>
                    <span>{item.message || item.name || formatApiDetail(item)}</span>
                  </List.Item>
                )}
              />
            </div>
          ),
          okText: '仍然保存记录',
          cancelText: '取消保存',
          okType: 'primary',
          onOk: async () => {
            await savePublishRecords(values, targets, task, true);
            await afterPublishRecordsSaved(values, targets, true);
          },
        });
        return;
      }
      message.error('保存发布记录失败: ' + formatApiError(error));
    }
  };

  const handleDeletePublishRecord = (record) => {
    Modal.confirm({
      title: '确认删除这条发布记录？',
      content: record.title || record.url || record.platform,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await publishRecordsApi.delete(record.id);
          message.success('发布记录已删除');
          loadPublishRecords();
        } catch (error) {
          message.error('删除发布记录失败: ' + (error.response?.data?.detail || error.message));
        }
      },
    });
  };

  const getDraftProjectId = (draft) => {
    if (!draft) return null;
    const task = tasks.find((item) => item.id === draft.task_id);
    return task?.project_id || null;
  };

  const getDraftTask = (draft) => {
    if (!draft) return null;
    return tasks.find((item) => item.id === draft.task_id) || null;
  };

  const loadDraftFeedbacks = async (draft) => {
    const projectId = getDraftProjectId(draft);
    if (!projectId || !draft?.id) {
      setDraftFeedbacks([]);
      return;
    }
    try {
      const res = await writingMemoryApi.listFeedbacks({ project_id: projectId, include_folded: true });
      setDraftFeedbacks((res.data || []).filter((item) => item.draft_id === draft.id));
    } catch (error) {
      setDraftFeedbacks([]);
    }
  };

  const buildFeedbackContext = (savedFeedback, values = {}) => {
    return [
      '以下是 AI 根据用户原始反馈优化后的文章重写提示词。请只按优化后提示词修改上一版草稿，不要照抄或扩写用户原话。',
      savedFeedback?.diff_summary ? `优化后重写提示词：${savedFeedback.diff_summary}` : '',
      savedFeedback?.rule_text ? `同时遵守长期规则：${savedFeedback.rule_text}` : '',
      savedFeedback?.rule_category ? `规则分类：${savedFeedback.rule_category}` : '',
      (!savedFeedback?.diff_summary && values.comment) ? `兜底重写要求：${values.comment}` : '',
      '请基于上一版草稿重新生成一版文章，必须做实质性改写，并保持项目事实、问题矩阵、文章类型和输出格式稳定。',
    ].filter(Boolean).join('\n');
  };

  const handleCreateDraftFeedback = async (values) => {
    const projectId = getDraftProjectId(viewingDraft);
    const task = getDraftTask(viewingDraft);
    if (!projectId) {
      message.warning('无法定位草稿所属项目，请从内容任务进入草稿后再记录反馈');
      return;
    }
    if (!task) {
      message.warning('无法定位草稿所属内容任务，请刷新任务列表后重试');
      return;
    }
    if (!values.rating && !values.comment && !values.rule_text) {
      message.warning('请至少填写评分、反馈说明或沉淀规则中的一项');
      return;
    }
    setFeedbackSubmitting(true);
    try {
      const feedbackRes = await writingMemoryApi.createFeedback({
        project_id: projectId,
        draft_id: viewingDraft.id,
        feedback_type: values.feedback_type,
        rating: values.rating,
        comment: values.comment,
        rule_text: values.rule_text,
        rule_category: values.rule_category || '语言风格',
        source: 'manual',
      });
      const savedFeedback = feedbackRes.data;
      setLastAppliedFeedback(savedFeedback);
      setDraftFeedbacks((prev) => [savedFeedback, ...prev]);
      feedbackForm.resetFields();

      const feedbackContext = buildFeedbackContext(savedFeedback, values);
      message.loading({ content: '反馈已记录，正在按反馈重新生成文章...', key: 'feedback-regenerate', duration: 0 });
      const generated = await contentDraftsApi.generate(task.id, {
        content_type: task.content_type || 'brand_intro',
        platform: 'media',
        source_draft_id: viewingDraft.id,
        feedback_context: feedbackContext,
      });
      const nextDraft = generated.data?.draft;
      if (nextDraft) {
        setViewingDraft(nextDraft);
        draftForm.setFieldsValue({
          title: nextDraft.title,
          body: nextDraft.body,
          status: nextDraft.status,
          risk_level: nextDraft.risk_level,
        });
        setDraftFeedbacks([]);
      }
      loadDrafts();
      message.success({ content: '已根据反馈重新生成一版草稿', key: 'feedback-regenerate' });
    } catch (error) {
      const detail = error.code === 'ECONNABORTED'
        ? '生成时间过长，请稍后重试；如果模型响应较慢，可以减少文章长度或换响应更快的模型。'
        : (error.response?.data?.detail || error.message);
      message.error({ content: '反馈或重新生成失败: ' + detail, key: 'feedback-regenerate' });
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const taskColumns = [
    {
      title: '所属项目',
      dataIndex: 'project_name',
      key: 'project_name',
      ellipsis: true,
      render: (name, record) => name || projects.find((project) => project.id === record.project_id)?.name || <Text type="danger">未绑定有效项目</Text>,
    },
    {
      title: '关联问题',
      dataIndex: 'representative_question',
      key: 'representative_question',
      ellipsis: true,
      render: (question, record) => question || record.group_intent_name || <Text type="secondary">未关联</Text>,
    },
    {
      title: '知识资产',
      dataIndex: 'knowledge_assets',
      key: 'knowledge_assets',
      render: (assets) => {
        const items = assets || [];
        if (!items.length) {
          return <Text type="secondary">自动推荐/未绑定</Text>;
        }
        return (
          <Space wrap size={4}>
            {items.slice(0, 3).map((asset) => (
              <Tag key={asset.id} color="cyan">
                {asset.title || asset.knowledge_layer || '知识资产'}
              </Tag>
            ))}
            {items.length > 3 && <Tag>+{items.length - 3}</Tag>}
          </Space>
        );
      },
    },
    { title: '内容类型', dataIndex: 'content_type', key: 'content_type' },
    {
      title: '层级',
      dataIndex: 'layer',
      key: 'layer',
      render: (l) => (
        <Tag color={l === 'verification_layer' ? 'blue' : l === 'pool_layer' ? 'green' : l === 'weight_layer' ? 'orange' : 'purple'}>
          {layerLabels[l] || l}
        </Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (p) => (
        <Badge color={p === 'high' ? 'red' : p === 'medium' ? 'orange' : 'blue'} text={p === 'high' ? '高' : p === 'medium' ? '中' : '低'} />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => (
        <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>
      ),
    },
    {
      title: '截止日期',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 132,
      render: (d) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          {formatTaskDueDate(d)}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<RobotOutlined />} onClick={() => openGenerateModal(record)}>
            生成草稿
          </Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteTask(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const draftColumns = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '目标平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (value) => platformLabels[value] || value || '媒体稿',
    },
    {
      title: '草稿版本',
      dataIndex: 'draft_version',
      key: 'draft_version',
      render: (value) => value || '-',
    },
    { title: '版本', dataIndex: 'version', key: 'version' },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (r) => <Tag color={r === 'high' ? 'red' : r === 'medium' ? 'orange' : 'green'}>{r === 'high' ? '高' : r === 'medium' ? '中' : '低'}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => openDraftModal(record)}>
            查看
          </Button>
          <Button type="link" icon={<CheckCircleOutlined />} onClick={() => handleValidatePublishReady(record)}>
            发布检查
          </Button>
          <Button type="link" icon={<LinkOutlined />} onClick={() => openPublishModal(record)}>
            记录发布
          </Button>
          <Button type="link" icon={<RobotOutlined />} onClick={() => handleWebBridgePublishAssist(record)}>
            发布助手
          </Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteDraft(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const channelColumns = [
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (value) => platformLabels[value] || value,
    },
    { title: '账号名称', dataIndex: 'account_name', key: 'account_name', ellipsis: true },
    {
      title: '账号类型',
      dataIndex: 'account_type',
      key: 'account_type',
      render: (value) => <Tag>{value === 'owned' ? '自有账号' : value}</Tag>,
    },
    {
      title: '发布权限',
      dataIndex: 'publish_permission',
      key: 'publish_permission',
      render: (value) => <Tag color={value ? 'green' : 'orange'}>{value ? '可发布' : '需确认'}</Tag>,
    },
    {
      title: '风险',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (value) => <Tag color={value === 'high' ? 'red' : value === 'medium' ? 'orange' : 'green'}>{value === 'high' ? '高' : value === 'medium' ? '中' : '低'}</Tag>,
    },
    {
      title: '最近发布',
      dataIndex: 'last_publish_at',
      key: 'last_publish_at',
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteChannelAccount(record)}>
          删除
        </Button>
      ),
    },
  ];

  const publishRecordColumns = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '所属项目',
      dataIndex: 'project_name',
      key: 'project_name',
      ellipsis: true,
      render: (value) => value || '-',
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (value, record) => (
        <Space>
          <span>{platformLabels[value] || value}</span>
          {record.channel_account_name && <Tag>{record.channel_account_name}</Tag>}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value) => <Tag color={value === 'published' ? 'green' : value === 'failed' ? 'red' : 'orange'}>{value === 'published' ? '已发布' : value === 'failed' ? '失败' : '待发布'}</Tag>,
    },
    {
      title: '收录',
      dataIndex: 'is_indexed',
      key: 'is_indexed',
      render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '已收录' : '未确认'}</Tag>,
    },
    {
      title: '发布时间',
      dataIndex: 'published_at',
      key: 'published_at',
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '链接',
      dataIndex: 'url',
      key: 'url',
      width: 118,
      ellipsis: true,
      render: (value) => value ? (
        <a href={value} target="_blank" rel="noreferrer" style={{ whiteSpace: 'nowrap' }}>
          打开链接
        </a>
      ) : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeletePublishRecord(record)}>
          删除
        </Button>
      ),
    },
  ];

  const renderFeedbackSummary = (item) => (
    <Space direction="vertical" size={2} style={{ width: '100%' }}>
      <Space wrap>
        <Tag color={item.feedback_type === 'rule' ? 'purple' : 'blue'}>{item.feedback_type}</Tag>
        {item.rating && <Tag color="green">{item.rating}</Tag>}
        {item.rule_category && <Tag>{item.rule_category}</Tag>}
        <Text type="secondary">{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</Text>
      </Space>
      {item.diff_summary && (
        <Paragraph style={{ marginBottom: 0 }}>
          <Text strong>优化后提示词：</Text>{item.diff_summary}
        </Paragraph>
      )}
      {item.rule_text && <Text type="secondary">长期规则：{item.rule_text}</Text>}
      {item.comment && <Text type="secondary">原始反馈：{item.comment}</Text>}
    </Space>
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>内容管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateTaskModal}>
          新建内容任务
        </Button>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><FileTextOutlined /> 内容任务 ({tasks.length})</span>} key="1">
          <Spin spinning={loading}>
            <Table columns={taskColumns} dataSource={tasks} rowKey="id" locale={{ emptyText: '暂无内容任务' }} />
          </Spin>
        </TabPane>

        <TabPane tab={<span><EditOutlined /> 稿件草稿 ({drafts.length})</span>} key="2">
          <Spin spinning={loading}>
            <Table columns={draftColumns} dataSource={drafts} rowKey="id" locale={{ emptyText: '暂无草稿' }} />
          </Spin>
        </TabPane>

        <TabPane tab={<span><CheckCircleOutlined /> 发布检查</span>} key="3">
          <Empty description='请在"稿件草稿"标签页中选择草稿进行发布检查' image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </TabPane>

        <TabPane tab={<span><LinkOutlined /> 发布渠道 ({channelAccounts.length})</span>} key="4">
          <Space style={{ marginBottom: 16 }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateChannelModal}>
              添加发布渠道
            </Button>
          </Space>
          <Spin spinning={loading}>
            <Table columns={channelColumns} dataSource={channelAccounts} rowKey="id" locale={{ emptyText: '暂无发布渠道' }} />
          </Spin>
        </TabPane>

        <TabPane tab={<span><LinkOutlined /> 发布记录 ({publishRecords.length})</span>} key="5">
          <Spin spinning={loading}>
            <Table columns={publishRecordColumns} dataSource={publishRecords} rowKey="id" locale={{ emptyText: '暂无发布记录' }} />
          </Spin>
        </TabPane>
      </Tabs>

      {/* 新建任务Modal */}
      <Modal title="新建内容任务" open={taskModalVisible} onOk={() => taskForm.submit()} onCancel={() => setTaskModalVisible(false)} width={760}>
        <Form form={taskForm} layout="vertical" onFinish={handleCreateTask}>
          <Form.Item name="project_id" label="所属项目" rules={[{ required: true, message: '请选择项目' }]}>
            <Select
              placeholder="请选择项目"
              disabled={projects.length === 0}
              showSearch
              optionFilterProp="children"
              onChange={(projectId) => {
                taskForm.setFieldsValue({
                  group_id: undefined,
                  question_id: undefined,
                  question_link: undefined,
                  knowledge_asset_ids: [],
                });
                loadQuestionGroups(projectId);
                loadKnowledgeAssets(projectId);
              }}
            >
              {projects.map((project) => (
                <Option key={project.id} value={project.id}>
                  {project.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="question_link" label="关联问题矩阵">
            <Select
              allowClear
              placeholder={questionGroups.length > 0 ? '请选择问题组或具体承接问题' : '该项目暂无问题矩阵，可先去项目详情生成'}
              disabled={questionGroups.length === 0}
              showSearch
              optionFilterProp="label"
              optionLabelProp="title"
              listHeight={360}
              dropdownStyle={{ maxHeight: 420, overflow: 'auto', minWidth: 520, maxWidth: 760 }}
            >
              {questionGroups.map((group) => {
                const enabledQuestions = (group.questions || []).filter((question) => question.enabled !== false);
                const groupTitle = `【${layerLabels[group.layer] || group.layer}】${group.representative_question || group.intent_name}`;
                return (
                  <OptGroup key={group.id} label={groupTitle}>
                    <Option
                      key={`group:${group.id}`}
                      value={`group:${group.id}`}
                      label={`只关联问题组 ${groupTitle}`}
                      title={group.representative_question || group.intent_name}
                    >
                      <Space size={6} align="start" style={{ maxWidth: 720, whiteSpace: 'normal', lineHeight: '20px' }}>
                        <Tag color="blue">问题组</Tag>
                        <span>{`只关联代表问题：${group.representative_question || group.intent_name}`}</span>
                      </Space>
                    </Option>
                    {enabledQuestions.map((question) => {
                      const searchText = [
                        groupTitle,
                        question.question_text,
                        question.question_type,
                        question.tags,
                        question.keyword_breakdown,
                      ].filter(Boolean).join(' ');
                      return (
                        <Option
                          key={`question:${question.id}`}
                          value={`question:${question.id}`}
                          label={searchText}
                          title={question.question_text}
                        >
                          <Space direction="vertical" size={0} style={{ maxWidth: 720, whiteSpace: 'normal', lineHeight: '20px', padding: '2px 0' }}>
                            <span>{question.question_text}</span>
                            <Text type="secondary" style={{ fontSize: 12, lineHeight: '18px' }}>
                              {`${layerLabels[group.layer] || group.layer} · ${question.question_type || '问题'} · P${question.priority ?? '-'}`}
                            </Text>
                          </Space>
                        </Option>
                      );
                    })}
                  </OptGroup>
                );
              })}
            </Select>
          </Form.Item>
          <Form.Item
            name="knowledge_asset_ids"
            label="关联项目知识资产"
            extra="可不选。留空时，系统会按关联问题的知识需求自动推荐；手动选择后会优先使用你选中的资料。"
          >
            <Select
              mode="multiple"
              allowClear
              loading={knowledgeAssetsLoading}
              disabled={knowledgeAssetsLoading || knowledgeAssets.length === 0}
              placeholder={knowledgeAssets.length > 0 ? '选择可用于本次写作的知识资产' : '该项目暂无知识资产，可先到项目知识库导入资料'}
              optionFilterProp="label"
              listHeight={320}
              dropdownStyle={{ maxHeight: 380, overflow: 'auto', minWidth: 520, maxWidth: 760 }}
            >
              {knowledgeAssets.map((asset) => {
                const label = [
                  asset.title,
                  asset.content,
                  asset.tags,
                  asset.knowledge_layer,
                  asset.business_use,
                  asset.evidence_level,
                ].filter(Boolean).join(' ');
                return (
                  <Option key={asset.id} value={asset.id} label={label}>
                    <Space direction="vertical" size={0} style={{ maxWidth: 720, whiteSpace: 'normal', lineHeight: '20px', padding: '2px 0' }}>
                      <Space wrap size={4}>
                        <Text strong>{asset.title || '未命名知识资产'}</Text>
                        <Tag color="blue">{asset.knowledge_layer || 'other'}</Tag>
                        <Tag color={asset.evidence_level === 'verified' || asset.evidence_level === 'official' ? 'green' : 'default'}>
                          {asset.evidence_level || 'unverified'}
                        </Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12, lineHeight: '18px' }}>
                        {String(asset.content || '').slice(0, 80)}
                      </Text>
                    </Space>
                  </Option>
                );
              })}
            </Select>
          </Form.Item>
          <Form.Item name="content_type" label="内容类型" rules={[{ required: true }]}>
            <Select placeholder="选择内容类型">
              <Option value="brand_intro">品牌介绍</Option>
              <Option value="product">产品介绍</Option>
              <Option value="case_study">案例</Option>
              <Option value="recommendation">推荐/选购指南</Option>
              <Option value="faq">FAQ</Option>
              <Option value="pr">PR稿</Option>
            </Select>
          </Form.Item>
          <Form.Item name="layer" label="内容层级" initialValue="verification_layer">
            <Select placeholder="选择层级">
              <Option value="verification_layer">基础验证层</Option>
              <Option value="pool_layer">入池层</Option>
              <Option value="weight_layer">权重提升层</Option>
              <Option value="conversion_layer">转化承接层</Option>
            </Select>
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="medium">
            <Radio.Group>
              <Radio value="high">高</Radio>
              <Radio value="medium">中</Radio>
              <Radio value="low">低</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* 生成草稿Modal */}
      <Modal
        title={`生成草稿: ${generatingTask?.content_type || ''}`}
        open={generateModalVisible}
        onOk={() => generateForm.submit()}
        onCancel={() => {
          setGenerateModalVisible(false);
          setGeneratingTask(null);
        }}
        confirmLoading={generating}
      >
        <Form form={generateForm} layout="vertical" onFinish={handleGenerate}>
          <Form.Item name="content_type" label="内容类型">
            <Input disabled />
          </Form.Item>
          <Form.Item name="platforms" label="目标平台（可多选）" initialValue={['media']}>
            <Select mode="multiple" placeholder="选择一个或多个发布平台">
              {Object.entries(platformLabels).map(([value, label]) => (
                <Option key={value} value={value}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Alert
            message="生成说明"
            description={(
              <Space direction="vertical" size={4}>
                <Text>
                  系统会优先基于已确认的品牌事实库生成可发布草稿；每个平台会按各自规则控制结构、字数、引流方式和高风险表达。
                </Text>
                <Text type="secondary">
                  推荐平台：
                  {getRecommendedPlatformsForTask(generatingTask || {})
                    .map((platform) => platformLabels[platform] || platform)
                    .join('、')}
                  。你可以按实际发布计划增删。
                </Text>
              </Space>
            )}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        </Form>
      </Modal>

      {/* 草稿详情Modal */}
      <Modal
        title={viewingDraft?.title || '草稿详情'}
        open={draftModalVisible}
        onOk={() => draftForm.submit()}
        onCancel={() => setDraftModalVisible(false)}
        width={800}
        footer={[
          <Button key="close" onClick={() => setDraftModalVisible(false)}>关闭</Button>,
          <Button key="save" type="primary" onClick={() => draftForm.submit()}>保存修改</Button>,
        ]}
      >
        <Form form={draftForm} layout="vertical" onFinish={handleUpdateDraft}>
          <Form.Item name="title" label="标题">
            <Input />
          </Form.Item>
          <Form.Item name="body" label="正文">
            <TextArea rows={12} />
          </Form.Item>
          <Form.Item name="platform" label="目标平台">
            <Select>
              {Object.entries(platformLabels).map(([value, label]) => (
                <Option key={value} value={value}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              {Object.entries(statusLabels).map(([key, label]) => (
                <Option key={key} value={key}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级">
            <Radio.Group>
              <Radio value="low">低</Radio>
              <Radio value="medium">中</Radio>
              <Radio value="high">高</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>

        {viewingDraft?.fact_refs && (
          <>
            <Divider />
            <Text strong>事实引用</Text>
            <Paragraph type="secondary" style={{ marginTop: 4 }}>
              系统命中的已确认事实库条目，用来追踪文章里的事实依据，方便发布前核验。
            </Paragraph>
            <div style={{ whiteSpace: 'pre-wrap', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
              {viewingDraft.fact_refs}
            </div>
          </>
        )}

        <Divider />
        {lastAppliedFeedback && (
          <Alert
            message="刚刚应用到新版本的反馈"
            description={renderFeedbackSummary(lastAppliedFeedback)}
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <List
          size="small"
          header={<Text strong>当前草稿反馈记录 ({draftFeedbacks.length})</Text>}
          dataSource={draftFeedbacks}
          locale={{ emptyText: '当前草稿暂无反馈' }}
          renderItem={(item) => (
            <List.Item>
              {renderFeedbackSummary(item)}
            </List.Item>
          )}
          style={{ marginBottom: 16 }}
        />

        <Text strong>记录写作反馈并重新生成</Text>
        <Form
          form={feedbackForm}
          layout="vertical"
          onFinish={handleCreateDraftFeedback}
          initialValues={{ feedback_type: 'comment', rule_category: '语言风格' }}
          style={{ marginTop: 12 }}
        >
          <Form.Item name="feedback_type" label="反馈类型">
            <Radio.Group>
              <Radio value="comment">修改意见</Radio>
              <Radio value="rule">沉淀规则</Radio>
              <Radio value="rating">评分</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="rating" label="评分">
            <Select allowClear placeholder="可选">
              <Option value="like">满意</Option>
              <Option value="dislike">不满意</Option>
              <Option value="neutral">一般</Option>
            </Select>
          </Form.Item>
          <Form.Item name="comment" label="反馈说明">
            <TextArea rows={2} placeholder="例如：太像广告，缺少资质编号说明；标题没有带地区词" />
          </Form.Item>
          <Form.Item name="rule_text" label="要沉淀的偏好/规则原文">
            <Input placeholder="可口语化描述，系统会先优化成重写提示词和长期规则" />
          </Form.Item>
          <Form.Item name="rule_category" label="规则分类">
            <Select>
              <Option value="语言风格">语言风格</Option>
              <Option value="标题偏好">标题偏好</Option>
              <Option value="事实合规">事实合规</Option>
              <Option value="平台适配">平台适配</Option>
            </Select>
          </Form.Item>
          <Button type="primary" loading={feedbackSubmitting} onClick={() => feedbackForm.submit()}>
            记录反馈并重新生成
          </Button>
        </Form>
      </Modal>

      {/* 添加发布渠道Modal */}
      <Modal
        title="添加发布渠道"
        open={channelModalVisible}
        onOk={() => channelForm.submit()}
        onCancel={() => setChannelModalVisible(false)}
        width={560}
      >
        <Form form={channelForm} layout="vertical" onFinish={handleCreateChannelAccount}>
          <Form.Item name="platform" label="平台" rules={[{ required: true, message: '请选择平台' }]}>
            <Select placeholder="请选择平台">
              {Object.entries(platformLabels).map(([value, label]) => (
                <Option key={value} value={value}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="account_name" label="账号名称" rules={[{ required: true, message: '请填写账号名称' }]}>
            <Input placeholder="例如：蒙霁空天智能公众号" />
          </Form.Item>
          <Form.Item name="account_type" label="账号类型">
            <Select>
              <Option value="owned">自有账号</Option>
              <Option value="partner">合作媒体</Option>
              <Option value="third_party">第三方渠道</Option>
            </Select>
          </Form.Item>
          <Form.Item name="publish_permission" label="是否有发布权限">
            <Radio.Group>
              <Radio value={true}>可直接发布</Radio>
              <Radio value={false}>需人工确认</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="login_required" label="是否需要登录">
            <Radio.Group>
              <Radio value={true}>需要</Radio>
              <Radio value={false}>不需要</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="publisher_url" label="发布编辑页 URL">
            <Input placeholder="例如：https://mp.weixin.qq.com/，用于 WebBridge 打开发文页面" />
          </Form.Item>
          <Form.Item name="title_selector" label="标题输入框选择器（可选）">
            <Input placeholder="平台页面复杂时填写，例如 input[placeholder*=标题]" />
          </Form.Item>
          <Form.Item name="body_selector" label="正文编辑器选择器（可选）">
            <Input placeholder="平台页面复杂时填写，例如 .editor 或 [contenteditable=true]" />
          </Form.Item>
          <Form.Item name="risk_level" label="发布风险">
            <Radio.Group>
              <Radio value="low">低</Radio>
              <Radio value="medium">中</Radio>
              <Radio value="high">高</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* WebBridge发布助手Modal */}
      <Modal
        title="WebBridge 发布助手"
        open={publishAssistVisible}
        onCancel={() => setPublishAssistVisible(false)}
        footer={[
          <Button key="copy" onClick={copyPublishPackage} disabled={!publishAssistResult?.content_package}>
            复制标题正文
          </Button>,
          <Button key="close" type="primary" onClick={() => setPublishAssistVisible(false)}>
            关闭
          </Button>,
        ]}
        width={760}
      >
        <Spin spinning={publishAssistLoading}>
          {!publishAssistResult ? (
            <Empty description="正在准备发布助手" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Alert
                message={publishAssistResult.webbridge?.ok ? '发布页已打开' : '需要人工处理'}
                description={
                  publishAssistResult.webbridge?.message
                  || (publishAssistResult.can_publish ? '已生成发布包，请手动复制到平台。' : '草稿未通过发布检查。')
                }
                type={publishAssistResult.webbridge?.ok ? 'success' : publishAssistResult.can_publish ? 'warning' : 'error'}
                showIcon
              />
              {publishAssistResult.issues?.length > 0 && (
                <List
                  header={<Text strong>发布检查问题</Text>}
                  size="small"
                  dataSource={publishAssistResult.issues}
                  renderItem={(item) => <List.Item>{typeof item === 'string' ? item : item.message || JSON.stringify(item)}</List.Item>}
                />
              )}
              <div>
                <Text strong>发布平台：</Text>
                <Text>{platformLabels[publishAssistResult.content_package?.platform] || publishAssistResult.content_package?.platform || '-'}</Text>
                {publishAssistResult.publisher_url && (
                  <>
                    <Divider type="vertical" />
                    <a href={publishAssistResult.publisher_url} target="_blank" rel="noreferrer">打开编辑页</a>
                  </>
                )}
              </div>
              <div>
                <Text strong>标题</Text>
                <Input value={publishAssistResult.content_package?.title || ''} readOnly style={{ marginTop: 8 }} />
              </div>
              <div>
                <Text strong>正文</Text>
                <TextArea rows={12} value={publishAssistResult.content_package?.body || ''} readOnly style={{ marginTop: 8 }} />
              </div>
              <Alert
                message="不会自动点击最终发布"
                description="WebBridge 只负责打开页面和预填内容。请人工核对事实、格式、图片和平台提示后，再在平台内点击发布；发布完成后回到系统保存发布记录和链接。"
                type="info"
                showIcon
              />
            </Space>
          )}
        </Spin>
      </Modal>

      {/* 记录发布Modal */}
      <Modal
        title="记录发布结果"
        open={publishModalVisible}
        onOk={() => publishForm.submit()}
        onCancel={() => {
          setPublishModalVisible(false);
          setPublishingDraft(null);
        }}
        width={620}
      >
        <Alert
          message="这是人工发布记录"
          description="这里先记录文章已经发布到哪个平台、链接是什么。后续检测和客户报告会基于这些记录判断 GEO 优化是否生效。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form form={publishForm} layout="vertical" onFinish={handleCreatePublishRecord}>
          <Form.Item
            name="publish_targets"
            label="发布目标"
            rules={[{ required: true, message: '请选择发布目标，或直接输入平台名称' }]}
          >
            <Select
              mode="tags"
              allowClear
              tokenSeparators={[',', '，', '\n']}
              placeholder={channelAccounts.length > 0 ? '可多选渠道账号，也可直接输入平台名' : '直接输入平台名，例如 抖音、本地官网、行业媒体'}
            >
              {channelAccounts.length > 0 && (
                <Option value="__channel_hint__" disabled>已维护渠道账号</Option>
              )}
              {channelAccounts.map((account) => (
                <Option key={account.id} value={`account:${account.id}`}>
                  {`${platformLabels[account.platform] || account.platform} / ${account.account_name}`}
                </Option>
              ))}
              <Option value="__platform_hint__" disabled>手动选择平台</Option>
              {Object.entries(platformLabels).map(([value, label]) => (
                <Option key={value} value={`platform:${value}`}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="title" label="发布标题" rules={[{ required: true, message: '请填写发布标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="urls_text"
            label="发布链接"
            extra="可先留空。多平台发布时建议每行填写：平台=链接，例如：公众号=https://...；知乎=https://..."
          >
            <TextArea rows={3} placeholder={'可先留空，发布完成后再补链接\n多平台示例：\n公众号=https://...\n知乎=https://...'} />
          </Form.Item>
          <Form.Item name="status" label="发布状态">
            <Select>
              <Option value="published">已发布</Option>
              <Option value="pending">待发布</Option>
              <Option value="failed">发布失败</Option>
            </Select>
          </Form.Item>
          <Form.Item name="is_indexed" label="是否已确认收录">
            <Radio.Group>
              <Radio value={false}>未确认</Radio>
              <Radio value={true}>已收录</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* 发布检查Modal */}
      <Modal
        title="发布就绪检查"
        open={validationModalVisible}
        onCancel={() => setValidationModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setValidationModalVisible(false)}>关闭</Button>,
        ]}
      >
        {validationResult && (
          <div>
            <Alert
              message={
                validationResult.can_publish
                  ? (validationResult.issues?.length ? '可以发布，但有风险提示' : '✅ 可以通过发布检查')
                  : '❌ 存在阻塞问题'
              }
              type={validationResult.can_publish ? (validationResult.issues?.length ? 'warning' : 'success') : 'error'}
              showIcon
              style={{ marginBottom: 16 }}
            />

            {validationResult.issues?.length > 0 && (
              <List
                size="small"
                header={<Text strong>问题清单 ({validationResult.total_issues} 项)</Text>}
                dataSource={validationResult.issues}
                renderItem={(item) => (
                  <List.Item>
                    <Space>
                      <WarningOutlined style={{ color: item.severity === 'high' ? '#ff4d4f' : '#faad14' }} />
                      <Text type={item.severity === 'high' ? 'danger' : 'warning'}>
                        {item.message}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}

            {validationResult.fact_references?.length > 0 && (
              <>
                <Divider />
                <Text strong>事实引用 ({validationResult.fact_references.length} 条)</Text>
                <List
                  size="small"
                  dataSource={validationResult.fact_references}
                  renderItem={(item) => (
                    <List.Item>
                      <Tag color="blue">{item.fact_type}</Tag>
                      <Text ellipsis style={{ maxWidth: 300 }}>{item.wording}</Text>
                    </List.Item>
                  )}
                />
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

export default ContentManagement;
