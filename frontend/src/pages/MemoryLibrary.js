import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { DeleteOutlined, EditOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { projectsApi, writingMemoryApi } from '../services/api';

const { Option } = Select;
const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const profileSectionLabels = {
  style_preferences: '写作风格',
  title_preferences: '标题偏好',
  constraints: '合规边界',
  platform_habits: '平台习惯',
};

const profileFieldLabels = {
  tone: '整体语气',
  sentence_style: '句式要求',
  banned_words: '避免用词',
  must_contain: '标题需包含',
  preferred_style: '标题风格',
  examples: '参考标题',
  no_false_promises: '禁止虚假承诺',
  no_competitor_bashing: '禁止贬低竞品',
  price_disclaimer: '价格表述要求',
  accuracy_required: '必须准确核验',
  word_count: '建议字数',
  style: '平台风格',
  emoji_level: '表情符号',
  formatting: '排版要求',
};

const profileSectionColors = {
  style_preferences: 'blue',
  title_preferences: 'purple',
  constraints: 'orange',
  platform_habits: 'green',
};

const profileTextTranslations = {
  'natural, conversational, first-person narrative, avoid official propaganda tone': '自然、口语化、第一人称叙事，避免官方宣传腔',
  'objective educational introduction or science popularization, no marketing traces': '客观的教育科普介绍，减少营销痕迹',
  'short sentences, active voice, each paragraph starts with scene or emotion to evoke resonance, avoid lengthy modifiers and passive voice, replace empty verbs like 自在 or 致力于 with specific actions or outcomes': '短句为主，使用主动语态；每段开头尽量有具体场景或情绪，避免过长修饰和被动句；少用“旨在”“致力于”这类空泛动词，改成具体动作或结果',
  "short sentences, active voice, each paragraph starts with scene or emotion to evoke resonance, avoid lengthy modifiers and passive voice, replace empty verbs like '旨在' or '致力于' with specific actions or outcomes": '短句为主，使用主动语态；每段开头尽量有具体场景或情绪，避免过长修饰和被动句；少用“旨在”“致力于”这类空泛动词，改成具体动作或结果',
  'first-person narrative, specific time/place/scene details, natural flow, avoid official tone, use short paragraphs and subheadings if needed': '第一人称叙事，补充具体时间、地点和场景细节；表达自然，避免官方腔；必要时用短段落和小标题',
  'clear paragraph breaks, use subheadings for sections, bold key terms sparingly': '段落分明，分节时使用小标题，关键术语可少量加粗',
  low: '低',
  medium: '中',
  high: '高',
};

const phraseTranslations = [
  ['natural', '自然'],
  ['conversational', '口语化'],
  ['first-person narrative', '第一人称叙事'],
  ['avoid official propaganda tone', '避免官方宣传腔'],
  ['avoid official tone', '避免官方腔'],
  ['short sentences', '短句为主'],
  ['active voice', '主动语态'],
  ['each paragraph starts with scene or emotion to evoke resonance', '每段开头尽量有具体场景或情绪来引发共鸣'],
  ['avoid lengthy modifiers and passive voice', '避免过长修饰和被动句'],
  ["replace empty verbs like '旨在' or '致力于' with specific actions or outcomes", '少用“旨在”“致力于”这类空泛动词，改成具体动作或结果'],
  ['with specific actions or outcomes', '改成具体动作或结果'],
  ['objective educational introduction', '客观教育介绍'],
  ['science popularization', '科普表达'],
  ['no marketing traces', '减少营销痕迹'],
  ['specific time/place/scene details', '具体时间、地点和场景细节'],
  ['natural flow', '表达自然'],
  ['clear paragraph breaks', '段落分明'],
  ['use subheadings', '使用小标题'],
  ['bold key terms sparingly', '少量加粗关键词'],
  ['emoji_level', '表情符号'],
];

const localizeProfileText = (value) => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return trimmed;
  if (profileTextTranslations[trimmed]) return profileTextTranslations[trimmed];
  const hasChinese = /[\u4e00-\u9fa5]/.test(trimmed);
  const hasEnglish = /[a-zA-Z]/.test(trimmed);
  if (!hasEnglish || hasChinese) {
    let mixed = trimmed;
    phraseTranslations.forEach(([from, to]) => {
      mixed = mixed.replace(new RegExp(from, 'gi'), to);
    });
    return mixed;
  }
  let translated = trimmed;
  phraseTranslations.forEach(([from, to]) => {
    translated = translated.replace(new RegExp(from, 'gi'), to);
  });
  return translated === trimmed ? `建议按中文规则理解：${trimmed}` : translated;
};

const localizeProfileValue = (value) => {
  if (Array.isArray(value)) return value.map((item) => localizeProfileValue(item));
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, entryValue]) => [key, localizeProfileValue(entryValue)])
    );
  }
  return localizeProfileText(value);
};

const safeProfileValue = (value) => {
  if (!value) return null;
  if (typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch (error) {
      return value;
    }
  }
  return value;
};

const isEmptyProfileValue = (value) => {
  if (value === null || value === undefined || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value).length === 0;
  return false;
};

const formatProfileKey = (key) => profileFieldLabels[key] || key;

const renderProfileValue = (value) => {
  const localizedValue = localizeProfileValue(value);
  if (isEmptyProfileValue(localizedValue)) {
    return <Text type="secondary">暂无</Text>;
  }
  if (typeof localizedValue === 'boolean') {
    return <Tag color={localizedValue ? 'green' : 'default'}>{localizedValue ? '需要' : '不需要'}</Tag>;
  }
  if (Array.isArray(localizedValue)) {
    return (
      <Space wrap size={[6, 6]}>
        {localizedValue.map((item, index) => (
          <Tag key={`${String(item)}-${index}`}>{String(item)}</Tag>
        ))}
      </Space>
    );
  }
  if (typeof localizedValue === 'object') {
    if ('min' in localizedValue || 'max' in localizedValue) {
      const min = localizedValue.min || 0;
      const max = localizedValue.max || 0;
      return <Text>{min && max ? `${min}-${max} 字` : `${min || max} 字左右`}</Text>;
    }
    const entries = Object.entries(localizedValue).filter(([, entryValue]) => !isEmptyProfileValue(entryValue));
    if (!entries.length) return <Text type="secondary">暂无</Text>;
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        {entries.map(([key, entryValue]) => (
          <div key={key}>
            <Text type="secondary">{formatProfileKey(key)}：</Text>
            {renderProfileValue(entryValue)}
          </div>
        ))}
      </Space>
    );
  }
  return <Text>{String(localizedValue)}</Text>;
};

const splitLines = (value) => String(value || '')
  .split(/\r?\n|[,，、]/)
  .map((item) => item.trim())
  .filter(Boolean);

const joinLines = (value) => Array.isArray(value) ? value.join('\n') : '';

const profileToFormValues = (profile) => {
  const style = localizeProfileValue(safeProfileValue(profile?.style_preferences) || {});
  const title = localizeProfileValue(safeProfileValue(profile?.title_preferences) || {});
  const constraints = localizeProfileValue(safeProfileValue(profile?.constraints) || {});
  const platformHabits = localizeProfileValue(safeProfileValue(profile?.platform_habits) || {});
  return {
    tone: style.tone || '',
    sentence_style: style.sentence_style || '',
    banned_words: joinLines(style.banned_words),
    must_contain: joinLines(title.must_contain),
    preferred_style: title.preferred_style || '',
    examples: joinLines(title.examples),
    no_false_promises: constraints.no_false_promises !== false,
    no_competitor_bashing: constraints.no_competitor_bashing !== false,
    price_disclaimer: constraints.price_disclaimer || '',
    accuracy_required: joinLines(constraints.accuracy_required),
    platform_habits_text: Object.entries(platformHabits).map(([platform, habit]) => {
      const wordCount = habit?.word_count;
      const wordText = wordCount?.min || wordCount?.max
        ? `${wordCount.min || ''}-${wordCount.max || ''}字`
        : '';
      return [platform, wordText, habit?.style || '', habit?.formatting || ''].join('｜');
    }).join('\n'),
  };
};

const parseWordCount = (value) => {
  const numbers = String(value || '').match(/\d+/g) || [];
  if (!numbers.length) return undefined;
  if (numbers.length === 1) return { min: Number(numbers[0]), max: Number(numbers[0]) };
  return { min: Number(numbers[0]), max: Number(numbers[1]) };
};

const formValuesToProfilePayload = (values) => {
  const platformHabits = {};
  String(values.platform_habits_text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const [platform, wordText, style, formatting] = line.split(/[|｜]/).map((item) => item.trim());
      if (!platform) return;
      platformHabits[platform] = {
        ...(parseWordCount(wordText) ? { word_count: parseWordCount(wordText) } : {}),
        ...(style ? { style } : {}),
        ...(formatting ? { formatting } : {}),
      };
    });
  return {
    style_preferences: {
      tone: values.tone || '',
      sentence_style: values.sentence_style || '',
      banned_words: splitLines(values.banned_words),
    },
    title_preferences: {
      must_contain: splitLines(values.must_contain),
      preferred_style: values.preferred_style || '',
      examples: splitLines(values.examples),
    },
    constraints: {
      no_false_promises: values.no_false_promises !== false,
      no_competitor_bashing: values.no_competitor_bashing !== false,
      price_disclaimer: values.price_disclaimer || '',
      accuracy_required: splitLines(values.accuracy_required),
    },
    platform_habits: platformHabits,
  };
};

function MemoryLibrary() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [writingProfile, setWritingProfile] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [folding, setFolding] = useState(false);
  const [ruleForm] = Form.useForm();
  const [profileForm] = Form.useForm();
  const [feedbackForm] = Form.useForm();
  const [profileModalVisible, setProfileModalVisible] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [feedbackModalVisible, setFeedbackModalVisible] = useState(false);
  const [editingFeedback, setEditingFeedback] = useState(null);
  const [feedbackSaving, setFeedbackSaving] = useState(false);

  const loadProjects = async () => {
    try {
      const res = await projectsApi.list({ limit: 100 });
      const items = res.data || [];
      setProjects(items);
      if (!selectedProjectId && items.length > 0) {
        setSelectedProjectId(items[0].id);
      }
    } catch (error) {
      message.error('加载项目失败');
    }
  };

  const loadMemory = async (projectId = selectedProjectId) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [profileRes, feedbackRes] = await Promise.all([
        writingMemoryApi.getProfile(projectId),
        writingMemoryApi.listFeedbacks({ project_id: projectId }),
      ]);
      setWritingProfile(profileRes.data || null);
      setFeedbacks(feedbackRes.data || []);
    } catch (error) {
      message.error('加载记忆库失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadMemory(selectedProjectId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  const handleAddRule = async (values) => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    try {
      await writingMemoryApi.createFeedback({
        project_id: selectedProjectId,
        feedback_type: 'rule',
        rule_text: values.rule_text,
        rule_category: values.rule_category || '语言风格',
        source: 'manual',
      });
      message.success('AI已分析并加入记忆库');
      ruleForm.resetFields();
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('添加规则失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleFoldProfile = async () => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    setFolding(true);
    try {
      const res = await writingMemoryApi.foldProfile(selectedProjectId);
      message.success(`行文画像已更新，折叠 ${res.data.folded_feedbacks || 0} 条反馈`);
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('画像折叠失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setFolding(false);
    }
  };

  const openProfileEdit = () => {
    if (!writingProfile) return;
    profileForm.setFieldsValue(profileToFormValues(writingProfile));
    setProfileModalVisible(true);
  };

  const handleSaveProfile = async (values) => {
    if (!selectedProjectId) return;
    setProfileSaving(true);
    try {
      await writingMemoryApi.updateProfile(selectedProjectId, formValuesToProfilePayload(values));
      message.success('行文画像已更新');
      setProfileModalVisible(false);
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('保存行文画像失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setProfileSaving(false);
    }
  };

  const handleDeleteProfile = async () => {
    if (!selectedProjectId) return;
    try {
      await writingMemoryApi.deleteProfile(selectedProjectId);
      message.success('行文画像已删除');
      setWritingProfile(null);
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('删除行文画像失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openFeedbackEdit = (item) => {
    setEditingFeedback(item);
    feedbackForm.setFieldsValue({
      diff_summary: item.diff_summary,
      rule_text: item.rule_text,
      rule_category: item.rule_category || '语言风格',
      comment: item.comment,
      rating: item.rating,
      is_folded: item.is_folded,
    });
    setFeedbackModalVisible(true);
  };

  const handleSaveFeedback = async (values) => {
    if (!editingFeedback) return;
    setFeedbackSaving(true);
    try {
      await writingMemoryApi.updateFeedback(editingFeedback.id, values);
      message.success('反馈记录已更新');
      setFeedbackModalVisible(false);
      setEditingFeedback(null);
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('保存反馈失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setFeedbackSaving(false);
    }
  };

  const handleDeleteFeedback = async (id) => {
    try {
      await writingMemoryApi.deleteFeedback(id);
      message.success('反馈已删除');
      loadMemory(selectedProjectId);
    } catch (error) {
      message.error('删除反馈失败');
    }
  };

  const renderFeedbackSummary = (item) => (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space wrap>
        <Tag color={item.is_folded ? 'default' : 'blue'}>{item.is_folded ? '已折叠' : '未折叠'}</Tag>
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

  const renderProfileSection = (sectionKey, sectionValue) => {
    const value = localizeProfileValue(safeProfileValue(sectionValue) || {});
    if (isEmptyProfileValue(value)) {
      return (
        <Empty description="暂无规则" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      );
    }
    if (sectionKey === 'platform_habits') {
      return (
        <Space direction="vertical" size={10} style={{ width: '100%', maxHeight: 360, overflow: 'auto', paddingRight: 8 }}>
          {Object.entries(value).map(([platform, habit]) => (
            <div key={platform} style={{ padding: 12, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fafafa' }}>
              <Text strong>{platform}</Text>
              <div style={{ marginTop: 6 }}>{renderProfileValue(habit)}</div>
            </div>
          ))}
        </Space>
      );
    }
    return (
      <div style={{ maxHeight: 360, overflow: 'auto', paddingRight: 8 }}>
        <Descriptions
          column={1}
          size="small"
          colon={false}
          labelStyle={{ width: 120, color: '#8c8c8c', verticalAlign: 'top' }}
          contentStyle={{ lineHeight: '24px' }}
        >
          {Object.entries(value)
            .filter(([, entryValue]) => !isEmptyProfileValue(entryValue))
            .map(([key, entryValue]) => (
              <Descriptions.Item key={key} label={formatProfileKey(key)}>
                {renderProfileValue(entryValue)}
              </Descriptions.Item>
            ))}
        </Descriptions>
      </div>
    );
  };

  const renderProfileSummary = () => {
    const style = localizeProfileValue(safeProfileValue(writingProfile.style_preferences) || {});
    const title = localizeProfileValue(safeProfileValue(writingProfile.title_preferences) || {});
    const constraints = localizeProfileValue(safeProfileValue(writingProfile.constraints) || {});
    const platformHabits = localizeProfileValue(safeProfileValue(writingProfile.platform_habits) || {});
    const rawProfile = {
      style_preferences: writingProfile.style_preferences,
      title_preferences: writingProfile.title_preferences,
      constraints: writingProfile.constraints,
      platform_habits: writingProfile.platform_habits,
    };
    return (
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Space wrap>
            <Tag color="green">v{writingProfile.version}</Tag>
            <Tag>{writingProfile.feedback_count || 0} 条反馈</Tag>
            {writingProfile.last_folded_at && (
              <Text type="secondary">更新时间：{new Date(writingProfile.last_folded_at).toLocaleString()}</Text>
            )}
          </Space>
          <Space>
            <Button icon={<EditOutlined />} onClick={openProfileEdit}>编辑画像</Button>
            <Popconfirm title="确认删除当前行文画像？" description="删除后反馈记录仍会保留，可重新折叠生成画像。" onConfirm={handleDeleteProfile}>
              <Button danger icon={<DeleteOutlined />}>删除画像</Button>
            </Popconfirm>
          </Space>
        </div>
        <div style={{ padding: 12, border: '1px solid #f0f0f0', borderRadius: 8, background: '#fafafa' }}>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text strong>核心摘要</Text>
            <Space wrap size={[8, 8]}>
              {style.tone && <Tag color="blue">语气：{style.tone}</Tag>}
              {title.preferred_style && <Tag color="purple">标题：{title.preferred_style}</Tag>}
              {Array.isArray(title.must_contain) && title.must_contain.slice(0, 4).map((item) => (
                <Tag key={item}>{item}</Tag>
              ))}
              {Array.isArray(style.banned_words) && <Tag color="orange">避免用词 {style.banned_words.length} 个</Tag>}
              {Array.isArray(constraints.accuracy_required) && <Tag color="gold">需核验 {constraints.accuracy_required.length} 项</Tag>}
              {Object.keys(platformHabits).length > 0 && <Tag color="green">平台规则 {Object.keys(platformHabits).length} 个</Tag>}
            </Space>
          </Space>
        </div>
        <Collapse
          size="middle"
          defaultActiveKey={['style_preferences']}
          items={[
            {
              key: 'style_preferences',
              label: (
                <Space wrap>
                  <Tag color={profileSectionColors.style_preferences}>{profileSectionLabels.style_preferences}</Tag>
                  <Text type="secondary">语气、句式、禁用词</Text>
                </Space>
              ),
              children: renderProfileSection('style_preferences', writingProfile.style_preferences),
            },
            {
              key: 'title_preferences',
              label: (
                <Space wrap>
                  <Tag color={profileSectionColors.title_preferences}>{profileSectionLabels.title_preferences}</Tag>
                  <Text type="secondary">标题关键词、标题风格、参考标题</Text>
                </Space>
              ),
              children: renderProfileSection('title_preferences', writingProfile.title_preferences),
            },
            {
              key: 'constraints',
              label: (
                <Space wrap>
                  <Tag color={profileSectionColors.constraints}>{profileSectionLabels.constraints}</Tag>
                  <Text type="secondary">风险表达、事实核验、价格约束</Text>
                </Space>
              ),
              children: renderProfileSection('constraints', writingProfile.constraints),
            },
            {
              key: 'platform_habits',
              label: (
                <Space wrap>
                  <Tag color={profileSectionColors.platform_habits}>{profileSectionLabels.platform_habits}</Tag>
                  <Text type="secondary">各平台字数、风格和排版习惯</Text>
                </Space>
              ),
              children: renderProfileSection('platform_habits', writingProfile.platform_habits),
            },
            {
              key: 'raw',
              label: '技术详情（原始结构，仅用于排查问题）',
              children: (
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 6, maxHeight: 260, overflow: 'auto' }}>
                  {JSON.stringify(rawProfile, null, 2)}
                </pre>
              ),
            },
          ]}
        />
      </Space>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 16 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>
            <ThunderboltOutlined /> 记忆库
          </h2>
          <Text type="secondary">管理项目的行文画像、AI优化后的重写提示词和长期写作规则。</Text>
        </div>
        <Space wrap>
          <Select
            style={{ width: 360 }}
            placeholder="选择项目"
            value={selectedProjectId}
            onChange={setSelectedProjectId}
          >
            {projects.map((project) => (
              <Option key={project.id} value={project.id}>{project.name}</Option>
            ))}
          </Select>
          <Button loading={loading} onClick={() => loadMemory()}>刷新</Button>
          <Button type="primary" loading={folding} onClick={handleFoldProfile}>折叠/更新画像</Button>
        </Space>
      </div>

      <Alert
        message="文章反馈会先被 AI 分析成优化后的重写提示词，再参与文章修改；原始反馈只作为证据保留。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Spin spinning={loading}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 16 }}>
            <Text strong>当前行文画像</Text>
            {writingProfile ? (
              <div style={{ marginTop: 12 }}>
                {renderProfileSummary()}
              </div>
            ) : (
              <Empty description="暂无行文画像。先添加反馈或规则，再点击折叠/更新画像。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>

          <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 16 }}>
            <Text strong>添加写作规则</Text>
            <Form form={ruleForm} layout="vertical" onFinish={handleAddRule} style={{ marginTop: 12 }}>
              <Form.Item name="rule_text" label="规则/偏好原始描述" rules={[{ required: true, message: '请输入规则内容' }]}>
                <TextArea rows={3} placeholder="可直接写你的想法，系统会先用 AI 归纳成可执行规则，例如：标题要带地区，别太广告，资质别瞎写" />
              </Form.Item>
              <Form.Item name="rule_category" label="规则分类" initialValue="语言风格">
                <Select style={{ maxWidth: 260 }}>
                  <Option value="语言风格">语言风格</Option>
                  <Option value="标题偏好">标题偏好</Option>
                  <Option value="事实合规">事实合规</Option>
                  <Option value="平台适配">平台适配</Option>
                  <Option value="内容结构">内容结构</Option>
                  <Option value="证据补齐">证据补齐</Option>
                </Select>
              </Form.Item>
              <Button type="primary" htmlType="submit">AI分析并加入记忆库</Button>
            </Form>
          </div>

          <List
            header={<Text strong>反馈与规则记录 ({feedbacks.length})</Text>}
            dataSource={feedbacks}
            locale={{ emptyText: '暂无反馈或规则' }}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => openFeedbackEdit(item)}>
                    编辑
                  </Button>,
                  <Button key="delete" type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteFeedback(item.id)}>
                    删除
                  </Button>,
                ]}
              >
                {renderFeedbackSummary(item)}
              </List.Item>
            )}
          />
        </Space>
      </Spin>

      <Modal
        title="编辑行文画像"
        open={profileModalVisible}
        onOk={() => profileForm.submit()}
        onCancel={() => setProfileModalVisible(false)}
        confirmLoading={profileSaving}
        width={760}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          message="这里编辑的是长期写作偏好，会影响后续文章生成。多项内容可一行写一个。"
          style={{ marginBottom: 16 }}
        />
        <Form form={profileForm} layout="vertical" onFinish={handleSaveProfile}>
          <Card size="small" title="写作风格" style={{ marginBottom: 12 }}>
            <Form.Item name="tone" label="整体语气">
              <Input placeholder="例如：自然、口语化、像真人经验分享，避免官方宣传腔" />
            </Form.Item>
            <Form.Item name="sentence_style" label="句式要求">
              <TextArea rows={2} placeholder="例如：短句为主，每段开头要有具体场景或情绪，不要空泛套话" />
            </Form.Item>
            <Form.Item name="banned_words" label="避免用词（一行一个）">
              <TextArea rows={4} placeholder={'例如：\n首选\n第一\n保证\n最专业'} />
            </Form.Item>
          </Card>

          <Card size="small" title="标题偏好" style={{ marginBottom: 12 }}>
            <Form.Item name="must_contain" label="标题需包含（一行一个）">
              <TextArea rows={3} placeholder={'例如：\n品牌名\n地区词\n核心服务词'} />
            </Form.Item>
            <Form.Item name="preferred_style" label="标题风格">
              <Input placeholder="例如：搜索友好、克制、不要标题党" />
            </Form.Item>
            <Form.Item name="examples" label="参考标题（一行一个）">
              <TextArea rows={3} />
            </Form.Item>
          </Card>

          <Card size="small" title="合规边界" style={{ marginBottom: 12 }}>
            <Form.Item name="no_false_promises" label="禁止虚假承诺">
              <Select>
                <Option value={true}>需要</Option>
                <Option value={false}>不需要</Option>
              </Select>
            </Form.Item>
            <Form.Item name="no_competitor_bashing" label="禁止贬低竞品">
              <Select>
                <Option value={true}>需要</Option>
                <Option value={false}>不需要</Option>
              </Select>
            </Form.Item>
            <Form.Item name="price_disclaimer" label="价格表述要求">
              <Input placeholder="例如：价格以官方最新确认信息为准，不能写死未确认优惠" />
            </Form.Item>
            <Form.Item name="accuracy_required" label="必须准确核验（一行一个）">
              <TextArea rows={3} placeholder={'例如：\n资质编号\n地址\n价格\n案例'} />
            </Form.Item>
          </Card>

          <Card size="small" title="平台习惯">
            <Form.Item
              name="platform_habits_text"
              label="平台习惯（一行一个：平台｜字数｜风格｜排版）"
            >
              <TextArea rows={5} placeholder={'例如：\n百家号｜800-1500字｜搜索友好、事实充分｜小标题清晰\n公众号｜1200-2200字｜叙事自然｜段落短一些'} />
            </Form.Item>
          </Card>
        </Form>
      </Modal>

      <Modal
        title="编辑反馈/规则记录"
        open={feedbackModalVisible}
        onOk={() => feedbackForm.submit()}
        onCancel={() => {
          setFeedbackModalVisible(false);
          setEditingFeedback(null);
        }}
        confirmLoading={feedbackSaving}
        width={700}
        destroyOnClose
      >
        <Form form={feedbackForm} layout="vertical" onFinish={handleSaveFeedback}>
          <Form.Item name="diff_summary" label="优化后提示词">
            <TextArea rows={4} placeholder="这条反馈转化后的可执行改稿提示词" />
          </Form.Item>
          <Form.Item name="rule_text" label="长期规则">
            <TextArea rows={3} placeholder="可沉淀到后续生成中的长期规则" />
          </Form.Item>
          <Form.Item name="rule_category" label="规则分类">
            <Select>
              <Option value="语言风格">语言风格</Option>
              <Option value="标题偏好">标题偏好</Option>
              <Option value="事实合规">事实合规</Option>
              <Option value="平台适配">平台适配</Option>
              <Option value="内容结构">内容结构</Option>
              <Option value="证据补齐">证据补齐</Option>
              <Option value="其他">其他</Option>
            </Select>
          </Form.Item>
          <Form.Item name="comment" label="原始反馈证据">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="rating" label="反馈倾向">
            <Select allowClear>
              <Option value="positive">正向</Option>
              <Option value="neutral">中性</Option>
              <Option value="negative">负向</Option>
            </Select>
          </Form.Item>
          <Form.Item name="is_folded" label="折叠状态">
            <Select>
              <Option value={false}>未折叠</Option>
              <Option value={true}>已折叠</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default MemoryLibrary;
