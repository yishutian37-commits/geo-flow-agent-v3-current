import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Spin, List, Tag, Button, Empty, Progress, Space } from 'antd';
import {
  ProjectOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  BarChartOutlined,
  WarningOutlined,
  ClockCircleOutlined,
  AuditOutlined,
  RocketOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { dashboardApi } from '../services/api';

const statusColors = {
  draft: 'default',
  confirmed: 'success',
  expired: 'error',
  disputed: 'warning',
  restricted: 'purple',
  active: 'processing',
  in_progress: 'processing',
  review: 'warning',
  approved: 'success',
  publish_ready: 'blue',
  published: 'green',
  completed: 'success',
  running: 'processing',
};

const statusLabels = {
  draft: '草稿',
  confirmed: '已确认',
  expired: '已过期',
  disputed: '争议中',
  restricted: '受限',
  active: '进行中',
  in_progress: '进行中',
  review: '待审核',
  approved: '已通过',
  publish_ready: '待发布',
  published: '已发布',
  completed: '已完成',
  running: '运行中',
};

function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      setLoading(true);
      try {
        const res = await dashboardApi.getStats();
        setStats(res.data);
      } catch (error) {
        // 静默失败
      } finally {
        setLoading(false);
      }
    };

    loadStats();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  const data = stats || {
    projects: { total: 0, active: 0 },
    facts: { total: 0, draft: 0, confirmed: 0, expired: 0, disputed: 0, restricted: 0 },
    tasks: { total: 0, draft: 0, in_progress: 0, review: 0, approved: 0, publish_ready: 0, published: 0 },
    monitoring: { total: 0, running: 0, completed: 0 },
    questions: { total: 0 },
    todos: [],
    recent_projects: [],
  };

  const factTotal = data.facts.total || 1;
  const taskTotal = data.tasks.total || 1;

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>仪表盘</h2>

      {/* 核心统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/projects')}>
            <Statistic
              title="进行中项目"
              value={data.projects.active}
              suffix={`/ ${data.projects.total}`}
              prefix={<ProjectOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/brand-facts')}>
            <Statistic
              title="已确认事实"
              value={data.facts.confirmed}
              suffix={`/ ${data.facts.total}`}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/content')}>
            <Statistic
              title="内容任务"
              value={data.tasks.in_progress}
              suffix={`进行中 / ${data.tasks.total}`}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/monitoring')}>
            <Statistic
              title="检测记录"
              value={data.monitoring.running}
              suffix={`运行中 / ${data.monitoring.total}`}
              prefix={<BarChartOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 第二行：待办 + 分布 + 最近项目 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 待办事项 */}
        <Col xs={24} lg={8}>
          <Card
            title={
              <Space>
                <WarningOutlined style={{ color: '#faad14' }} />
                <span>待办事项</span>
                {data.todos.length > 0 && <Tag color="red">{data.todos.length}</Tag>}
              </Space>
            }
          >
            {data.todos.length === 0 ? (
              <Empty description="暂无待办事项" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={data.todos}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(item.link)}
                      >
                        去处理 <RightOutlined />
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Tag color={item.priority === 'high' ? 'red' : item.priority === 'medium' ? 'orange' : 'blue'}>
                            {item.priority === 'high' ? '高' : item.priority === 'medium' ? '中' : '低'}
                          </Tag>
                          <span>{item.title}</span>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        {/* 事实库分布 */}
        <Col xs={24} lg={8}>
          <Card title={<Space><AuditOutlined /><span>事实库状态</span></Space>}>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>已确认</span>
                <span>{data.facts.confirmed} ({Math.round((data.facts.confirmed / factTotal) * 100)}%)</span>
              </div>
              <Progress percent={Math.round((data.facts.confirmed / factTotal) * 100)} size="small" strokeColor="#52c41a" showInfo={false} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>待确认</span>
                <span>{data.facts.draft} ({Math.round((data.facts.draft / factTotal) * 100)}%)</span>
              </div>
              <Progress percent={Math.round((data.facts.draft / factTotal) * 100)} size="small" strokeColor="#faad14" showInfo={false} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>已过期</span>
                <span>{data.facts.expired} ({Math.round((data.facts.expired / factTotal) * 100)}%)</span>
              </div>
              <Progress percent={Math.round((data.facts.expired / factTotal) * 100)} size="small" strokeColor="#ff4d4f" showInfo={false} />
            </div>
            <div>
              <Space wrap>
                {Object.entries(data.facts).filter(([k]) => k !== 'total').map(([key, value]) => (
                  <Tag key={key} color={statusColors[key] || 'default'}>
                    {statusLabels[key] || key}: {value}
                  </Tag>
                ))}
              </Space>
            </div>
          </Card>
        </Col>

        {/* 内容任务分布 */}
        <Col xs={24} lg={8}>
          <Card title={<Space><RocketOutlined /><span>内容任务状态</span></Space>}>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>草稿</span>
                <span>{data.tasks.draft}</span>
              </div>
              <Progress percent={Math.round((data.tasks.draft / taskTotal) * 100)} size="small" showInfo={false} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>进行中</span>
                <span>{data.tasks.in_progress}</span>
              </div>
              <Progress percent={Math.round((data.tasks.in_progress / taskTotal) * 100)} size="small" strokeColor="#1890ff" showInfo={false} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span>待审核</span>
                <span>{data.tasks.review}</span>
              </div>
              <Progress percent={Math.round((data.tasks.review / taskTotal) * 100)} size="small" strokeColor="#faad14" showInfo={false} />
            </div>
            <div>
              <Space wrap>
                {Object.entries(data.tasks).filter(([k]) => k !== 'total').map(([key, value]) => (
                  <Tag key={key} color={statusColors[key] || 'default'}>
                    {statusLabels[key] || key}: {value}
                  </Tag>
                ))}
              </Space>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 第三行：最近项目 + 快速入口 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <ClockCircleOutlined />
                <span>最近活跃项目</span>
              </Space>
            }
            extra={<Button type="link" onClick={() => navigate('/projects')}>查看全部</Button>}
          >
            {data.recent_projects.length === 0 ? (
              <Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={data.recent_projects}
                renderItem={(project) => (
                  <List.Item
                    actions={[
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/projects/${project.id}`)}
                      >
                        详情 <RightOutlined />
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <span>{project.name}</span>
                          <Tag color="blue">{project.industry}</Tag>
                          <Tag color={statusColors[project.status] || 'default'}>
                            {statusLabels[project.status] || project.status}
                          </Tag>
                        </Space>
                      }
                      description={`最近更新: ${project.updated_at ? new Date(project.updated_at).toLocaleString() : '-'}`}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="快速入口">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button block icon={<ProjectOutlined />} onClick={() => navigate('/projects')}>
                项目管理
              </Button>
              <Button block icon={<CheckCircleOutlined />} onClick={() => navigate('/brand-facts')}>
                品牌事实库
              </Button>
              <Button block icon={<FileTextOutlined />} onClick={() => navigate('/content')}>
                内容管理
              </Button>
              <Button block icon={<BarChartOutlined />} onClick={() => navigate('/monitoring')}>
                监测分析
              </Button>
              <Button block icon={<RocketOutlined />} onClick={() => navigate('/ai-models')}>
                AI 模型配置
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default Dashboard;
