import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../services/api';

const { Title, Text } = Typography;

function Login() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [needsBootstrap, setNeedsBootstrap] = useState(false);

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await authApi.bootstrapStatus();
        setNeedsBootstrap(Boolean(res.data?.needs_bootstrap));
        if (res.data?.needs_bootstrap) {
          form.setFieldsValue({
            username: 'admin',
            email: 'admin@geoflow.app',
            full_name: 'Local Admin',
          });
        }
      } catch (error) {
        message.error(`读取登录状态失败：${error.response?.data?.detail || error.message}`);
      } finally {
        setChecking(false);
      }
    };
    loadStatus();
  }, [form]);

  const saveSession = (data) => {
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('current_user', JSON.stringify(data.user || {}));
  };

  const handleSubmit = async (values) => {
    setLoading(true);
    try {
      const res = needsBootstrap
        ? await authApi.bootstrapAdmin(values)
        : await authApi.login({ username: values.username, password: values.password });
      saveSession(res.data);
      message.success(needsBootstrap ? '管理员已初始化' : '登录成功');
      navigate('/');
    } catch (error) {
      message.error(`${needsBootstrap ? '初始化失败' : '登录失败'}：${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f5f7fb', padding: 24 }}>
      <Card style={{ width: '100%', maxWidth: 420 }} loading={checking}>
        <Title level={3} style={{ marginBottom: 8 }}>GEO Flow Agent V2.3</Title>
        <Text type="secondary">
          {needsBootstrap ? '首次使用，请创建本地管理员账号。' : '请输入账号密码进入系统。'}
        </Text>
        {needsBootstrap && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="只允许在系统没有任何用户时初始化管理员。"
          />
        )}
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          style={{ marginTop: 24 }}
        >
          <Form.Item name="username" label="用户名或邮箱" rules={[{ required: true, message: '请输入用户名或邮箱' }]}>
            <Input autoComplete="username" />
          </Form.Item>
          {needsBootstrap && (
            <>
              <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
                <Input autoComplete="email" />
              </Form.Item>
              <Form.Item name="full_name" label="姓名">
                <Input />
              </Form.Item>
            </>
          )}
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少 6 位' }]}>
            <Input.Password autoComplete={needsBootstrap ? 'new-password' : 'current-password'} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            {needsBootstrap ? '初始化管理员' : '登录'}
          </Button>
        </Form>
      </Card>
    </div>
  );
}

export default Login;
