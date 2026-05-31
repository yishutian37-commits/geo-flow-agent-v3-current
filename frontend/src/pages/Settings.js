import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
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

import { usersApi } from '../services/api';

const { Paragraph, Text, Title } = Typography;

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
  const [loading, setLoading] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState(null);
  const [form] = Form.useForm();
  const [passwordForm] = Form.useForm();
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

  useEffect(() => {
    loadUsers();
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
    </div>
  );
}

export default Settings;
