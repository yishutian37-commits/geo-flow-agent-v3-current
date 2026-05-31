import React from 'react';
import { Button, Layout, Menu, Space } from 'antd';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ProjectOutlined,
  FileTextOutlined,
  BarChartOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';

import Dashboard from './pages/Dashboard';
import Projects from './pages/Projects';
import ProjectDetail from './pages/ProjectDetail';
import ContentManagement from './pages/ContentManagement';
import Monitoring from './pages/Monitoring';
import BrandFacts from './pages/BrandFacts';
import AIModels from './pages/AIModels';
import MemoryLibrary from './pages/MemoryLibrary';
import Reports from './pages/Reports';
import Login from './pages/Login';
import Settings from './pages/Settings';

const { Header, Sider, Content } = Layout;

function readCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('current_user') || 'null');
  } catch {
    return null;
  }
}

function App() {
  const location = useLocation();
  const currentUser = readCurrentUser();

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('current_user');
    window.location.href = '/login';
  };

  if (location.pathname === '/login') {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
      </Routes>
    );
  }

  const selectedKey = location.pathname.startsWith('/projects')
    ? '/projects'
    : location.pathname;

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: <Link to="/">仪表盘</Link> },
    { key: '/projects', icon: <ProjectOutlined />, label: <Link to="/projects">项目管理</Link> },
    { key: '/brand-facts', icon: <CheckCircleOutlined />, label: <Link to="/brand-facts">品牌事实库</Link> },
    { key: '/content', icon: <FileTextOutlined />, label: <Link to="/content">内容管理</Link> },
    { key: '/monitoring', icon: <BarChartOutlined />, label: <Link to="/monitoring">监测分析</Link> },
    { key: '/reports', icon: <FileSearchOutlined />, label: <Link to="/reports">报告中心</Link> },
    { key: '/ai-models', icon: <ThunderboltOutlined />, label: <Link to="/ai-models">AI 模型</Link> },
    { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">系统设置</Link> },
    { key: '/memory', icon: <DatabaseOutlined />, label: <Link to="/memory">记忆库</Link> },
  ];

  return (
    <Layout className="geo-app-layout" style={{ minHeight: '100vh' }}>
      <Header
        style={{
          color: '#fff',
          fontSize: 18,
          fontWeight: 'bold',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>GEO Flow Agent V2.3</span>
        <Space size={12}>
          {currentUser ? (
            <>
              <span style={{ fontSize: 14, fontWeight: 400 }}>
                {currentUser.full_name || currentUser.username} · {currentUser.role}
              </span>
              <Button size="small" onClick={handleLogout}>退出</Button>
            </>
          ) : (
            <Link to="/login"><Button size="small">登录</Button></Link>
          )}
        </Space>
      </Header>
      <Layout className="geo-main-layout">
        <Sider className="geo-sidebar" theme="light" width={200}>
          <Menu mode="inline" selectedKeys={[selectedKey]} items={menuItems} />
        </Sider>
        <Content className="geo-page-content" style={{ margin: 16, padding: 24, background: '#fff' }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/content" element={<ContentManagement />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/brand-facts" element={<BrandFacts />} />
            <Route path="/ai-models" element={<AIModels />} />
            <Route path="/memory" element={<MemoryLibrary />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
