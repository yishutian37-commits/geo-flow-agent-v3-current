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

import { platformPoliciesApi, usersApi } from '../services/api';

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
  const [loading, setLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState(null);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState(null);
  const [form] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [policyForm] = Form.useForm();
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

  useEffect(() => {
    loadUsers();
    loadPlatformPolicies();
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
    </div>
  );
}

export default Settings;
