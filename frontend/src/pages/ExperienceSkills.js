import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
  Row,
  Col,
} from 'antd';
import { CheckCircleOutlined, DeleteOutlined, EditOutlined, HistoryOutlined, PlusOutlined, RollbackOutlined } from '@ant-design/icons';
import { experienceSkillsApi, projectsApi } from '../services/api';
import Table from '../components/SafeTable';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const scopeLabels = {
  project: '项目级',
  industry: '行业级',
  global: '全局级',
};

const sceneLabels = {
  article_writing: '文章生成',
  rewrite: '文章改写',
  question_generation: '问题生成',
  publish_check: '发布检查',
  monitoring_review: '监测复盘',
};

const typeLabels = {
  rule: '规则',
  prompt_hint: '提示词',
  checklist: '检查清单',
  template: '模板',
  negative_example: '反例',
  workflow: '流程方法',
};

const sourceLabels = {
  feedback: '文章反馈',
  monitoring_review: '监测复盘',
  publish_check: '发布检查',
  manual: '手动添加',
};

const sourceColors = {
  feedback: 'purple',
  monitoring_review: 'blue',
  publish_check: 'orange',
  manual: 'default',
};

function extractError(error) {
  return error?.response?.data?.detail || error?.message || '未知错误';
}

function ExperienceSkills() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [skills, setSkills] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingSkill, setEditingSkill] = useState(null);
  const [saving, setSaving] = useState(false);
  const [versionModalVisible, setVersionModalVisible] = useState(false);
  const [selectedSkillForVersions, setSelectedSkillForVersions] = useState(null);
  const [skillVersions, setSkillVersions] = useState([]);
  const [versionLoading, setVersionLoading] = useState(false);
  const [form] = Form.useForm();

  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const stats = useMemo(() => ({
    pending: suggestions.filter((item) => item.status === 'pending').length,
    active: skills.filter((item) => item.status === 'active').length,
    project: skills.filter((item) => item.scope === 'project').length,
    industry: skills.filter((item) => item.scope === 'industry').length,
  }), [skills, suggestions]);

  const loadProjects = useCallback(async () => {
    try {
      const res = await projectsApi.list({ limit: 200 });
      const items = res.data || [];
      setProjects(items);
      if (!selectedProjectId && items.length) {
        setSelectedProjectId(items[0].id);
      }
    } catch (error) {
      message.error('加载项目失败：' + extractError(error));
    }
  }, [selectedProjectId]);

  const loadData = useCallback(async (projectId = selectedProjectId) => {
    setLoading(true);
    try {
      const params = projectId ? { project_id: projectId } : {};
      const [skillRes, suggestionRes] = await Promise.all([
        experienceSkillsApi.list(params),
        experienceSkillsApi.listSuggestions({ ...params, status: 'pending' }),
      ]);
      setSkills(skillRes.data || []);
      setSuggestions(suggestionRes.data || []);
    } catch (error) {
      message.error('加载经验技能失败：' + extractError(error));
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (selectedProjectId) {
      loadData(selectedProjectId);
    }
  }, [loadData, selectedProjectId]);

  const openCreateModal = () => {
    setEditingSkill(null);
    form.setFieldsValue({
      scope: 'project',
      project_id: selectedProjectId,
      industry: selectedProject?.industry,
      trigger_scene: 'article_writing',
      skill_type: 'rule',
      status: 'active',
      confidence: 0.6,
    });
    setModalVisible(true);
  };

  const openEditModal = (record) => {
    setEditingSkill(record);
    form.setFieldsValue({
      ...record,
      revision_reason: '手动修订',
      change_type: 'revise',
    });
    setModalVisible(true);
  };

  const handleSave = async (values) => {
    setSaving(true);
    try {
      const { revision_reason, change_type, ...skillValues } = values;
      const payload = {
        ...skillValues,
        project_id: skillValues.scope === 'project' ? skillValues.project_id : undefined,
        industry: skillValues.scope === 'industry' ? skillValues.industry : undefined,
      };
      if (editingSkill) {
        await experienceSkillsApi.revise(editingSkill.id, {
          ...payload,
          revision_reason: revision_reason || '手动修订',
          change_type: change_type || 'revise',
        });
        message.success('经验技能已更新');
      } else {
        await experienceSkillsApi.create(payload);
        message.success('经验技能已创建');
      }
      setModalVisible(false);
      form.resetFields();
      await loadData();
    } catch (error) {
      message.error('保存失败：' + extractError(error));
    } finally {
      setSaving(false);
    }
  };

  const handleApproveSuggestion = async (record) => {
    try {
      await experienceSkillsApi.approveSuggestion(record.id);
      message.success('已确认并启用经验技能');
      await loadData();
    } catch (error) {
      message.error('确认失败：' + extractError(error));
    }
  };

  const handleToggleSkill = async (record) => {
    const nextStatus = record.status === 'active' ? 'archived' : 'active';
    try {
      await experienceSkillsApi.update(record.id, { status: nextStatus });
      message.success(nextStatus === 'active' ? '经验技能已启用' : '经验技能已停用');
      await loadData();
    } catch (error) {
      message.error('状态更新失败：' + extractError(error));
    }
  };

  const handleDeleteSkill = async (record) => {
    try {
      await experienceSkillsApi.delete(record.id);
      message.success('经验技能已删除');
      await loadData();
    } catch (error) {
      message.error('删除失败：' + extractError(error));
    }
  };

  const openVersionModal = async (record) => {
    setSelectedSkillForVersions(record);
    setVersionModalVisible(true);
    setVersionLoading(true);
    try {
      const res = await experienceSkillsApi.listVersions(record.id);
      setSkillVersions(res.data || []);
    } catch (error) {
      message.error('加载版本历史失败：' + extractError(error));
    } finally {
      setVersionLoading(false);
    }
  };

  const handleRollbackVersion = async (versionRecord) => {
    if (!selectedSkillForVersions) return;
    setVersionLoading(true);
    try {
      const res = await experienceSkillsApi.rollbackVersion(selectedSkillForVersions.id, versionRecord.version);
      const updatedSkill = res.data;
      setSelectedSkillForVersions(updatedSkill);
      const versionRes = await experienceSkillsApi.listVersions(updatedSkill.id);
      setSkillVersions(versionRes.data || []);
      message.success(`已回滚到 v${versionRecord.version}，并生成新版本 v${updatedSkill.version}`);
      await loadData();
    } catch (error) {
      message.error('回滚失败：' + extractError(error));
    } finally {
      setVersionLoading(false);
    }
  };

  const suggestionColumns = [
    {
      title: '建议',
      dataIndex: 'suggestion_text',
      key: 'suggestion_text',
      render: (value, record) => (
        <Space direction="vertical" size={4}>
          <Text strong>{record.name || '未命名技能建议'}</Text>
          <Paragraph style={{ marginBottom: 0 }}>{value}</Paragraph>
          {record.evidence && <Text type="secondary">证据：{record.evidence}</Text>}
        </Space>
      ),
    },
    {
      title: '范围/场景',
      key: 'meta',
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Tag color="blue">{scopeLabels[record.suggested_scope] || record.suggested_scope}</Tag>
          <Tag color="green">{sceneLabels[record.trigger_scene] || record.trigger_scene}</Tag>
          <Tag>{typeLabels[record.skill_type] || record.skill_type}</Tag>
        </Space>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 120,
      render: (value) => <Tag color={sourceColors[value] || 'default'}>{sourceLabels[value] || value || '未知'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, record) => (
        <Button type="primary" size="small" icon={<CheckCircleOutlined />} onClick={() => handleApproveSuggestion(record)}>
          确认启用
        </Button>
      ),
    },
  ];

  const skillColumns = [
    {
      title: '技能',
      dataIndex: 'name',
      key: 'name',
      render: (value, record) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Text strong>{value}</Text>
            <Tag color="blue">v{record.version || record.current_version || 1}</Tag>
          </Space>
          <Paragraph style={{ marginBottom: 0 }}>{record.content}</Paragraph>
        </Space>
      ),
    },
    {
      title: '范围/场景',
      key: 'meta',
      width: 240,
      render: (_, record) => (
        <Space wrap>
          <Tag color={record.scope === 'project' ? 'blue' : record.scope === 'industry' ? 'orange' : 'purple'}>
            {scopeLabels[record.scope] || record.scope}
          </Tag>
          <Tag color="green">{sceneLabels[record.trigger_scene] || record.trigger_scene}</Tag>
          <Tag>{typeLabels[record.skill_type] || record.skill_type}</Tag>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '启用中' : '已停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      render: (_, record) => (
        <Space wrap>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(record)}>编辑</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => openVersionModal(record)}>历史</Button>
          <Button size="small" onClick={() => handleToggleSkill(record)}>
            {record.status === 'active' ? '停用' : '启用'}
          </Button>
          <Popconfirm title="确认删除这条经验技能吗？" onConfirm={() => handleDeleteSkill(record)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const versionColumns = [
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 90,
      render: (value) => <Tag color="blue">v{value}</Tag>,
    },
    {
      title: '内容快照',
      key: 'snapshot',
      render: (_, record) => (
        <Space direction="vertical" size={4}>
          <Space wrap>
            <Text strong>{record.name}</Text>
            <Tag>{scopeLabels[record.scope] || record.scope}</Tag>
            <Tag color="green">{sceneLabels[record.trigger_scene] || record.trigger_scene}</Tag>
            <Tag>{typeLabels[record.skill_type] || record.skill_type}</Tag>
          </Space>
          <Paragraph style={{ marginBottom: 0 }}>{record.content}</Paragraph>
          {record.revision_reason && <Text type="secondary">修订原因：{record.revision_reason}</Text>}
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'change_type',
      key: 'change_type',
      width: 110,
      render: (value) => {
        const labels = { create: '创建', update: '编辑', revise: '修订', rollback: '回滚' };
        const colors = { create: 'green', update: 'blue', revise: 'purple', rollback: 'orange' };
        return <Tag color={colors[value] || 'default'}>{labels[value] || value || '未知'}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_, record) => {
        const currentVersion = selectedSkillForVersions?.version || selectedSkillForVersions?.current_version;
        return (
          <Popconfirm
            title={`确认回滚到 v${record.version} 吗？`}
            onConfirm={() => handleRollbackVersion(record)}
            disabled={record.version === currentVersion}
          >
            <Button
              size="small"
              icon={<RollbackOutlined />}
              disabled={record.version === currentVersion}
            >
              回滚
            </Button>
          </Popconfirm>
        );
      },
    },
  ];

  return (
    <div>
      <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>经验技能库</h2>
          <Text type="secondary">把项目反馈、文章修改和监测复盘沉淀成可复用经验，人工确认后参与后续生成。</Text>
        </div>
        <Space>
          <Select
            style={{ width: 360 }}
            placeholder="选择项目"
            value={selectedProjectId}
            onChange={setSelectedProjectId}
            options={projects.map((project) => ({ label: project.name, value: project.id }))}
          />
          <Button onClick={() => loadData()} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>手动添加技能</Button>
        </Space>
      </Space>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="技能不会自动越级复用"
        description="项目反馈默认生成项目级待确认建议；确认后才会进入文章生成。涉及证书编号、价格、地址、案例等事实的内容不会自动升级为行业或全局技能。"
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card><Statistic title="待确认建议" value={stats.pending} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="启用技能" value={stats.active} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="项目级技能" value={stats.project} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="行业级技能" value={stats.industry} /></Card></Col>
      </Row>

      <Card title="待确认技能建议" style={{ marginBottom: 16 }}>
        <Table
          loading={loading}
          columns={suggestionColumns}
          dataSource={suggestions}
          rowKey="id"
          locale={{ emptyText: '暂无待确认建议。提交文章反馈后，系统会自动生成建议。' }}
        />
      </Card>

      <Card title="已沉淀经验技能">
        <Table
          loading={loading}
          columns={skillColumns}
          dataSource={skills}
          rowKey="id"
          locale={{ emptyText: '暂无经验技能' }}
        />
      </Card>

      <Modal
        title={editingSkill ? '编辑经验技能' : '手动添加经验技能'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        width={720}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="name" label="技能名称" rules={[{ required: true, message: '请输入技能名称' }]}>
            <Input placeholder="例如：本地口语化写作" />
          </Form.Item>
          <Form.Item name="content" label="技能内容" rules={[{ required: true, message: '请输入技能内容' }]}>
            <TextArea rows={4} placeholder="写清楚后续生成应该怎么做，以及不能做什么" />
          </Form.Item>
          {editingSkill && (
            <Form.Item name="revision_reason" label="本次修订原因" rules={[{ required: true, message: '请说明为什么修订' }]}>
              <Input placeholder="例如：补充平台发布风险、合并同类表达规则、回滚错误规则" />
            </Form.Item>
          )}
          <Space size={16} style={{ width: '100%' }} align="start">
            <Form.Item name="scope" label="适用范围" rules={[{ required: true }]}>
              <Select style={{ width: 160 }} options={[
                { label: '项目级', value: 'project' },
                { label: '行业级', value: 'industry' },
                { label: '全局级', value: 'global' },
              ]} />
            </Form.Item>
            <Form.Item name="project_id" label="所属项目">
              <Select
                style={{ width: 260 }}
                allowClear
                options={projects.map((project) => ({ label: project.name, value: project.id }))}
              />
            </Form.Item>
            <Form.Item name="industry" label="行业">
              <Input style={{ width: 180 }} placeholder="行业级时填写" />
            </Form.Item>
          </Space>
          <Space size={16} style={{ width: '100%' }} align="start">
            <Form.Item name="trigger_scene" label="触发场景" rules={[{ required: true }]}>
              <Select style={{ width: 180 }} options={[
                { label: '文章生成', value: 'article_writing' },
                { label: '文章改写', value: 'rewrite' },
                { label: '问题生成', value: 'question_generation' },
                { label: '发布检查', value: 'publish_check' },
                { label: '监测复盘', value: 'monitoring_review' },
              ]} />
            </Form.Item>
            <Form.Item name="skill_type" label="技能类型" rules={[{ required: true }]}>
              <Select style={{ width: 160 }} options={[
                { label: '规则', value: 'rule' },
                { label: '提示词', value: 'prompt_hint' },
                { label: '检查清单', value: 'checklist' },
                { label: '模板', value: 'template' },
                { label: '反例', value: 'negative_example' },
                { label: '流程方法', value: 'workflow' },
              ]} />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select style={{ width: 140 }} options={[
                { label: '启用', value: 'active' },
                { label: '停用', value: 'archived' },
              ]} />
            </Form.Item>
          </Space>
          {editingSkill && (
            <Form.Item name="change_type" hidden>
              <Input />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={selectedSkillForVersions ? `${selectedSkillForVersions.name} 的版本历史` : '版本历史'}
        open={versionModalVisible}
        onCancel={() => setVersionModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setVersionModalVisible(false)}>关闭</Button>,
        ]}
        width={980}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="回滚不会删除历史版本"
          description="回滚会基于选中的旧版本生成一个新的当前版本，旧版本仍然保留，方便继续追溯。"
        />
        <Table
          loading={versionLoading}
          columns={versionColumns}
          dataSource={skillVersions}
          rowKey="id"
          locale={{ emptyText: '暂无版本历史' }}
        />
      </Modal>
    </div>
  );
}

export default ExperienceSkills;
