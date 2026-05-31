import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  List,
  message,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { DeleteOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { projectsApi, writingMemoryApi } from '../services/api';

const { Option } = Select;
const { TextArea } = Input;
const { Text, Paragraph } = Typography;

function MemoryLibrary() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [writingProfile, setWritingProfile] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [folding, setFolding] = useState(false);
  const [ruleForm] = Form.useForm();

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
                <Tag color="green">v{writingProfile.version}</Tag>
                <Tag>{writingProfile.feedback_count || 0} 条反馈</Tag>
                <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                  {JSON.stringify({
                    style_preferences: writingProfile.style_preferences,
                    title_preferences: writingProfile.title_preferences,
                    constraints: writingProfile.constraints,
                    platform_habits: writingProfile.platform_habits,
                  }, null, 2)}
                </pre>
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
    </div>
  );
}

export default MemoryLibrary;
