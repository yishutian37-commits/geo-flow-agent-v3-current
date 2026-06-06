import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, SafetyOutlined } from '@ant-design/icons';

import { platformPoliciesApi, questionArchetypesApi, usersApi } from '../services/api';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

function readCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('current_user') || 'null');
  } catch {
    return null;
  }
}

function Settings() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [platformPolicies, setPlatformPolicies] = useState([]);
  const [questionArchetypes, setQuestionArchetypes] = useState([]);
  const [templateSuggestions, setTemplateSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [archetypeLoading, setArchetypeLoading] = useState(false);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState(null);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState(null);
  const [archetypeModalOpen, setArchetypeModalOpen] = useState(false);
  const [editingArchetype, setEditingArchetype] = useState(null);
  const [form] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [policyForm] = Form.useForm();
  const [archetypeForm] = Form.useForm();
  const currentUser = useMemo(readCurrentUser, []);
  const isAdmin = currentUser?.role === 'admin';

  const roleOptions = roles.map((role) => ({
    value: role.value,
    label: `${role.label} (${role.value})`,
  }));
  const roleLabels = Object.fromEntries(roles.map((role) => [role.value, role.label]));

  const loadUsers = async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const [roleRes, userRes] = await Promise.all([
        usersApi.listRoles(),
        usersApi.list({ limit: 500 }),
      ]);
      setRoles(roleRes.data?.roles || []);
      setUsers(userRes.data || []);
    } catch (error) {
      message.error('加载用户失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const loadPlatformPolicies = async () => {
    if (!isAdmin) return;
    setPolicyLoading(true);
    try {
      const policyRes = await platformPoliciesApi.list();
      setPlatformPolicies(policyRes.data || []);
    } catch (error) {
      message.error('加载平台规则失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setPolicyLoading(false);
    }
  };

  const loadQuestionArchetypes = async () => {
    if (!isAdmin) return;
    setArchetypeLoading(true);
    try {
      const res = await questionArchetypesApi.list();
      setQuestionArchetypes(res.data?.industries || []);
    } catch (error) {
      message.error('加载行业问题模板失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setArchetypeLoading(false);
    }
  };

  const loadQuestionLearningSuggestions = async () => {
    if (!isAdmin) return;
    setSuggestionLoading(true);
    try {
      const res = await questionArchetypesApi.suggestions({ limit: 200 });
      setTemplateSuggestions(res.data?.items || []);
    } catch (error) {
      message.error('加载模板优化建议失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSuggestionLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    loadPlatformPolicies();
    loadQuestionArchetypes();
    loadQuestionLearningSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const openCreate = () => {
    setEditingUser(null);
    form.resetFields();
    form.setFieldsValue({ role: 'viewer', is_active: true });
    setUserModalOpen(true);
  };

  const openEdit = (record) => {
    setEditingUser(record);
    form.resetFields();
    form.setFieldsValue({
      email: record.email,
      full_name: record.full_name,
      role: record.role,
      is_active: record.is_active,
    });
    setUserModalOpen(true);
  };

  const submitUser = async (values) => {
    try {
      if (editingUser) {
        await usersApi.update(editingUser.id, values);
        message.success('用户已更新');
      } else {
        await usersApi.create(values);
        message.success('用户已创建');
      }
      setUserModalOpen(false);
      await loadUsers();
    } catch (error) {
      message.error('保存用户失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openPassword = (record) => {
    setPasswordUser(record);
    passwordForm.resetFields();
    setPasswordModalOpen(true);
  };

  const submitPassword = async (values) => {
    try {
      await usersApi.resetPassword(passwordUser.id, { password: values.password });
      message.success('密码已重置');
      setPasswordModalOpen(false);
    } catch (error) {
      message.error('重置密码失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const deactivateUser = (record) => {
    Modal.confirm({
      title: '停用用户',
      content: `确认停用 ${record.full_name || record.username} 吗？停用后该账号不能再登录。`,
      okText: '停用',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await usersApi.deactivate(record.id);
          message.success('用户已停用');
          await loadUsers();
        } catch (error) {
          message.error('停用失败: ' + (error.response?.data?.detail || error.message));
        }
      },
    });
  };

  const listToText = (items = []) => (Array.isArray(items) ? items.join('\n') : '');

  const textToList = (value = '') => String(value || '')
    .split(/\r?\n|,|，/)
    .map((item) => item.trim())
    .filter(Boolean);

  const openPolicyEdit = (record) => {
    setEditingPolicy(record);
    policyForm.resetFields();
    policyForm.setFieldsValue({
      ...record,
      title_rules_text: listToText(record.title_rules),
      forbidden_patterns_text: listToText(record.forbidden_patterns),
      warning_patterns_text: listToText(record.warning_patterns),
      recommended_content_types_text: listToText(record.recommended_content_types),
    });
    setPolicyModalOpen(true);
  };

  const submitPlatformPolicy = async (values) => {
    if (!editingPolicy?.platform) return;
    const payload = {
      name: values.name,
      style: values.style,
      length: values.length,
      min_words: values.min_words,
      max_words: values.max_words,
      format: values.format,
      contact_policy: values.contact_policy,
      ai_label_required: values.ai_label_required,
      title_rules: textToList(values.title_rules_text),
      forbidden_patterns: textToList(values.forbidden_patterns_text),
      warning_patterns: textToList(values.warning_patterns_text),
      recommended_content_types: textToList(values.recommended_content_types_text),
    };
    try {
      await platformPoliciesApi.update(editingPolicy.platform, payload);
      message.success('平台规则已保存');
      setPolicyModalOpen(false);
      setEditingPolicy(null);
      await loadPlatformPolicies();
    } catch (error) {
      message.error('保存平台规则失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openArchetypeEdit = (record) => {
    setEditingArchetype(record);
    archetypeForm.resetFields();
    archetypeForm.setFieldsValue({
      raw_json: JSON.stringify(record.raw || {}, null, 2),
    });
    setArchetypeModalOpen(true);
  };

  const submitQuestionArchetype = async (values) => {
    if (!editingArchetype?.industry) return;
    let payload;
    try {
      payload = JSON.parse(values.raw_json || '{}');
    } catch (error) {
      message.error('行业模板不是合法 JSON，请检查括号、逗号和引号');
      return;
    }
    try {
      await questionArchetypesApi.update(editingArchetype.industry, payload);
      message.success('行业问题模板已保存');
      setArchetypeModalOpen(false);
      setEditingArchetype(null);
      await loadQuestionArchetypes();
      await loadQuestionLearningSuggestions();
    } catch (error) {
      message.error('保存行业问题模板失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const applyTemplateSuggestion = async (record) => {
    try {
      await questionArchetypesApi.applySuggestion(record);
      message.success('模板优化建议已写入行业模板库');
      await Promise.all([loadQuestionArchetypes(), loadQuestionLearningSuggestions()]);
    } catch (error) {
      message.error('应用模板优化建议失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const columns = [
    {
      title: '用户',
      key: 'user',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.full_name || record.username}</Text>
          <Text type="secondary">{record.username}</Text>
        </Space>
      ),
    },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => <Tag color={role === 'admin' ? 'red' : 'blue'}>{roleLabels[role] || role}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active) => active ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button type="link" onClick={() => openEdit(record)}>编辑</Button>
          <Button type="link" onClick={() => openPassword(record)}>重置密码</Button>
          <Button
            type="link"
            danger
            disabled={!record.is_active || record.id === currentUser?.id}
            onClick={() => deactivateUser(record)}
          >
            停用
          </Button>
        </Space>
      ),
    },
  ];

  const platformPolicyColumns = [
    {
      title: '平台',
      dataIndex: 'name',
      key: 'name',
      width: 150,
      fixed: 'left',
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value || record.platform}</Text>
          <Text type="secondary">{record.platform}</Text>
        </Space>
      ),
    },
    {
      title: '字数建议',
      dataIndex: 'length',
      key: 'length',
      width: 150,
    },
    {
      title: '结构',
      dataIndex: 'format',
      key: 'format',
      width: 220,
      ellipsis: true,
    },
    {
      title: '引流策略',
      dataIndex: 'contact_policy',
      key: 'contact_policy',
      width: 150,
      render: (value) => {
        const labels = {
          owned_channel_allowed: '自有渠道可承接',
          soft_reference_only: '只做弱提示',
          avoid_direct_contact: '避免直接引流',
        };
        const colors = {
          owned_channel_allowed: 'green',
          soft_reference_only: 'blue',
          avoid_direct_contact: 'orange',
        };
        return <Tag color={colors[value] || 'default'}>{labels[value] || value || '-'}</Tag>;
      },
    },
    {
      title: 'AIGC标识',
      dataIndex: 'ai_label_required',
      key: 'ai_label_required',
      width: 110,
      render: (value) => value ? <Tag color="purple">建议标识</Tag> : <Tag>不强制</Tag>,
    },
    {
      title: '适合内容',
      dataIndex: 'recommended_content_types',
      key: 'recommended_content_types',
      width: 260,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.slice(0, 4).map((item) => <Tag key={item} color="geekblue">{item}</Tag>)}
        </Space>
      ),
    },
    {
      title: '高风险词',
      dataIndex: 'forbidden_patterns',
      key: 'forbidden_patterns',
      width: 260,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.slice(0, 5).map((item) => <Tag key={item} color="red">{item}</Tag>)}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => openPolicyEdit(record)}>编辑</Button>
      ),
    },
  ];

  const questionArchetypeColumns = [
    {
      title: '行业',
      dataIndex: 'industry',
      key: 'industry',
      width: 180,
      fixed: 'left',
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          {record.extends && <Text type="secondary">继承：{record.extends}</Text>}
        </Space>
      ),
    },
    {
      title: '主体称呼',
      dataIndex: 'entity_label',
      key: 'entity_label',
      width: 110,
      render: (value) => <Tag color="blue">{value || '服务商'}</Tag>,
    },
    {
      title: '兜底服务词',
      key: 'fallback',
      width: 180,
      render: (_, record) => record.fallback_service || `品牌名 + ${record.fallback_service_suffix || '服务'}`,
    },
    {
      title: '验证问法',
      key: 'trust',
      width: 280,
      ellipsis: true,
      render: (_, record) => record.copy?.verified_question || record.copy?.trust_question || '-',
    },
    {
      title: '转化问法',
      key: 'conversion',
      width: 260,
      ellipsis: true,
      render: (_, record) => record.copy?.process_question || '-',
    },
    {
      title: '禁用词',
      dataIndex: 'forbidden_terms',
      key: 'forbidden_terms',
      width: 260,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.slice(0, 6).map((item) => <Tag key={item} color="orange">{item}</Tag>)}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => openArchetypeEdit(record)}>编辑</Button>
      ),
    },
  ];

  const templateSuggestionColumns = [
    {
      title: '行业',
      dataIndex: 'industry',
      key: 'industry',
      width: 160,
      fixed: 'left',
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">{record.events || 0} 条人工调整</Text>
        </Space>
      ),
    },
    {
      title: '建议新增禁用词',
      dataIndex: 'add_forbidden_terms',
      key: 'add_forbidden_terms',
      width: 240,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.length ? items.map((item) => <Tag color="orange" key={item}>{item}</Tag>) : <Text type="secondary">暂无</Text>}
        </Space>
      ),
    },
    {
      title: '正向样例',
      dataIndex: 'positive_examples',
      key: 'positive_examples',
      width: 360,
      render: (items = []) => (
        <Space direction="vertical" size={2}>
          {items.slice(0, 3).map((item) => <Text key={item} ellipsis>{item}</Text>)}
          {!items.length && <Text type="secondary">暂无</Text>}
        </Space>
      ),
    },
    {
      title: '反向样例',
      dataIndex: 'negative_examples',
      key: 'negative_examples',
      width: 360,
      render: (items = []) => (
        <Space direction="vertical" size={2}>
          {items.slice(0, 3).map((item) => <Text key={item} ellipsis>{item}</Text>)}
          {!items.length && <Text type="secondary">暂无</Text>}
        </Space>
      ),
    },
    {
      title: '建议原因',
      dataIndex: 'reason',
      key: 'reason',
      width: 320,
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Button
          type="link"
          onClick={() => Modal.confirm({
            title: '确认写入行业模板库？',
            content: '写入后会影响后续新生成的问题矩阵；已经存在的问题不会自动改变。',
            okText: '确认写入',
            cancelText: '取消',
            onOk: () => applyTemplateSuggestion(record),
          })}
        >
          确认写入
        </Button>
      ),
    },
  ];

  if (!isAdmin) {
    return (
      <div>
        <Title level={2}>系统设置</Title>
        <Alert
          type="warning"
          showIcon
          message="当前账号没有用户管理权限"
          description="用户与角色管理仅管理员可操作。你仍可以继续使用自己角色允许的项目、内容、监测等功能。"
        />
      </div>
    );
  }

  return (
    <div>
      <Space align="start" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={2}>系统设置</Title>
          <Paragraph type="secondary">
            管理本地应用账号与 RBAC 角色。关键操作会以后端登录用户为准写入确认人、审批人和发布人。
          </Paragraph>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建用户</Button>
        </Space>
      </Space>

      <Card
        title={<Space><SafetyOutlined /> 用户与角色</Space>}
        bodyStyle={{ padding: 0 }}
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={users}
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Card title="角色说明" style={{ marginTop: 16 }}>
        <Space wrap>
          {roles.map((role) => (
            <Tag key={role.value} color={role.value === 'admin' ? 'red' : 'blue'}>
              {role.label}: {role.description}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card
        title="平台适配规则"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadPlatformPolicies}>刷新规则</Button>}
      >
        <Paragraph type="secondary">
          这里展示文章生成、合规检查和发布建议共用的平台规则。生成平台稿时，系统会按这些规则控制结构、字数、引流方式和高风险表达。
        </Paragraph>
        <Table
          rowKey="platform"
          columns={platformPolicyColumns}
          dataSource={platformPolicies}
          loading={policyLoading}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 1420 }}
          size="small"
        />
      </Card>

      <Card
        title="行业问题模板"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadQuestionArchetypes}>刷新模板</Button>}
      >
        <Paragraph type="secondary">
          这里控制问题库生成时的行业主体称呼、可信验证问法、转化承接问法和行业禁用词。后续遇到相同行业时，系统会复用这些模板生成更稳定的问题矩阵。
        </Paragraph>
        <Table
          rowKey="industry"
          columns={questionArchetypeColumns}
          dataSource={questionArchetypes}
          loading={archetypeLoading}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 1360 }}
          size="small"
        />
      </Card>

      <Card
        title="问题模板优化建议"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadQuestionLearningSuggestions}>刷新建议</Button>}
      >
        <Paragraph type="secondary">
          用户新增、改写、删除或禁用问题后，系统会把这些人工调整汇总成模板优化建议。管理员确认后，才会写入行业模板库，供后续同类项目生成问题矩阵时复用。
        </Paragraph>
        <Table
          rowKey={(record) => `${record.industry}-${(record.feedback_ids || []).join('-')}`}
          columns={templateSuggestionColumns}
          dataSource={templateSuggestions}
          loading={suggestionLoading}
          pagination={{ pageSize: 6 }}
          scroll={{ x: 1560 }}
          size="small"
          locale={{ emptyText: '暂无待确认的模板优化建议' }}
        />
      </Card>

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={userModalOpen}
        onCancel={() => setUserModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submitUser}>
          {!editingUser && (
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input />
            </Form.Item>
          )}
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }, { min: 6, message: '至少 6 位' }]}>
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={`重置密码：${passwordUser?.full_name || passwordUser?.username || ''}`}
        open={passwordModalOpen}
        onCancel={() => setPasswordModalOpen(false)}
        onOk={() => passwordForm.submit()}
        destroyOnClose
      >
        <Form form={passwordForm} layout="vertical" onFinish={submitPassword}>
          <Form.Item name="password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '至少 6 位' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑平台规则：${editingPolicy?.name || editingPolicy?.platform || ''}`}
        open={policyModalOpen}
        onCancel={() => {
          setPolicyModalOpen(false);
          setEditingPolicy(null);
        }}
        onOk={() => policyForm.submit()}
        width={760}
        destroyOnClose
      >
        <Form form={policyForm} layout="vertical" onFinish={submitPlatformPolicy}>
          <Form.Item name="name" label="平台名称" rules={[{ required: true, message: '请填写平台名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="style" label="推荐风格">
            <TextArea rows={2} placeholder="例如：搜索友好、结构清晰、事实充分、弱广告" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="length" label="字数说明" style={{ flex: 1 }}>
              <Input placeholder="例如：500-3000字" />
            </Form.Item>
            <Form.Item name="min_words" label="最少字数">
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item name="max_words" label="最多字数">
              <InputNumber min={0} />
            </Form.Item>
          </Space>
          <Form.Item name="format" label="推荐结构">
            <TextArea rows={2} placeholder="例如：问题结论+判断标准+事实证据+建议" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="contact_policy" label="引流策略" style={{ flex: 1 }}>
              <Select>
                <Select.Option value="owned_channel_allowed">自有渠道可承接</Select.Option>
                <Select.Option value="soft_reference_only">只做弱提示</Select.Option>
                <Select.Option value="avoid_direct_contact">避免直接引流</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="ai_label_required" label="建议 AIGC 标识" valuePropName="checked">
              <Switch checkedChildren="建议" unCheckedChildren="不强制" />
            </Form.Item>
          </Space>
          <Form.Item name="title_rules_text" label="标题规则（一行一条）">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="forbidden_patterns_text" label="高风险/禁止表达（一行一个词）">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="warning_patterns_text" label="谨慎表达（一行一个词）">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="recommended_content_types_text" label="适合内容类型（一行一个）">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑行业问题模板：${editingArchetype?.industry || ''}`}
        open={archetypeModalOpen}
        onCancel={() => {
          setArchetypeModalOpen(false);
          setEditingArchetype(null);
        }}
        onOk={() => archetypeForm.submit()}
        width={860}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="修改后会影响后续新生成的问题库"
          description="已经生成并落库的旧问题不会自动改变；需要重新生成问题库或手动编辑旧问题。"
        />
        <Form form={archetypeForm} layout="vertical" onFinish={submitQuestionArchetype}>
          <Form.Item
            name="raw_json"
            label="模板 JSON"
            rules={[{ required: true, message: '请填写模板 JSON' }]}
          >
            <TextArea rows={18} style={{ fontFamily: 'Consolas, monospace' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default Settings;
