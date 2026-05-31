import React, { useState, useEffect } from 'react';
import { Button, Tag, Modal, Form, Input, Select, message, Spin, Space, InputNumber, Popconfirm } from 'antd';
import { PlusOutlined, EyeOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { projectsApi } from '../services/api';
import Table from '../components/SafeTable';

const { Option } = Select;

const INDUSTRY_OPTIONS = [
  { value: 'education_training', label: '教育培训' },
  { value: 'local_life', label: '本地生活' },
  { value: 'manufacturing_b2b', label: '制造业 B2B' },
  { value: 'consumer_brand', label: '消费品牌' },
  { value: 'professional_service', label: '专业服务' },
  { value: 'healthcare', label: '医疗健康' },
  { value: 'real_estate', label: '房地产' },
  { value: 'finance', label: '金融保险' },
  { value: 'e_commerce', label: '电商零售' },
  { value: 'technology', label: '科技互联网' },
  { value: 'manufacturing', label: '制造业' },
  { value: 'tourism', label: '旅游酒店' },
  { value: 'catering', label: '餐饮美食' },
  { value: 'automobile', label: '汽车服务' },
];

const STATUS_OPTIONS = [
  { value: 'active', label: '进行中', color: 'green' },
  { value: 'completed', label: '已完成', color: 'blue' },
  { value: 'archived', label: '已归档', color: 'default' },
];

const industryLabel = (value) => INDUSTRY_OPTIONS.find((item) => item.value === value)?.label || value;
const statusMeta = (value) => STATUS_OPTIONS.find((item) => item.value === value) || { label: value, color: 'default' };

function ProjectFormFields() {
  return (
    <>
      <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
        <Input placeholder="输入项目名称" />
      </Form.Item>
      <Form.Item name="industry" label="行业" rules={[{ required: true, message: '请选择行业' }]}>
        <Select placeholder="选择行业">
          {INDUSTRY_OPTIONS.map((item) => (
            <Option key={item.value} value={item.value}>{item.label}</Option>
          ))}
        </Select>
      </Form.Item>
      <Form.Item name="region" label="地区" rules={[{ required: true, message: '请输入地区' }]}>
        <Input placeholder="例如：包头" />
      </Form.Item>
      <Form.Item name="budget" label="预算（元）">
        <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="输入预算金额" />
      </Form.Item>
      <Form.Item name="target_ai_products" label="检测平台">
        <Input placeholder="例如：DeepSeek, 通义千问, Kimi" />
      </Form.Item>
      <Form.Item name="notes" label="备注">
        <Input.TextArea rows={3} placeholder="项目备注信息" />
      </Form.Item>
    </>
  );
}

function Projects() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingProject, setEditingProject] = useState(null);
  const [creating, setCreating] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const navigate = useNavigate();

  const loadProjects = async () => {
    setLoading(true);
    try {
      const res = await projectsApi.list({ limit: 100 });
      setProjects(res.data || []);
    } catch (error) {
      message.error('加载项目失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleCreate = async (values) => {
    setCreating(true);
    try {
      await projectsApi.create(values);
      message.success('项目创建成功');
      setCreateModalVisible(false);
      createForm.resetFields();
      loadProjects();
    } catch (error) {
      message.error('创建失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCreating(false);
    }
  };

  const openEditModal = (record) => {
    setEditingProject(record);
    editForm.setFieldsValue({
      name: record.name,
      industry: record.industry,
      region: record.region,
      budget: record.budget == null ? undefined : Number(record.budget),
      target_ai_products: record.target_ai_products,
      notes: record.notes,
      status: record.status,
    });
    setEditModalVisible(true);
  };

  const handleUpdate = async (values) => {
    if (!editingProject) return;
    setUpdating(true);
    try {
      await projectsApi.update(editingProject.id, values);
      message.success('项目已更新');
      setEditModalVisible(false);
      setEditingProject(null);
      editForm.resetFields();
      loadProjects();
    } catch (error) {
      message.error('更新失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUpdating(false);
    }
  };

  const handleDelete = async (record) => {
    setDeletingProjectId(record.id);
    try {
      await projectsApi.delete(record.id);
      message.success('项目已删除');
      loadProjects();
    } catch (error) {
      message.error('删除失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setDeletingProjectId(null);
    }
  };

  const columns = [
    { title: '项目名称', dataIndex: 'name', key: 'name' },
    {
      title: '行业',
      dataIndex: 'industry',
      key: 'industry',
      render: industryLabel,
    },
    { title: '地区', dataIndex: 'region', key: 'region' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const meta = statusMeta(status);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: '预算',
      dataIndex: 'budget',
      key: 'budget',
      render: (v) => (v ? `¥${Number(v).toLocaleString()}` : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => navigate(`/projects/${record.id}`)}>
            查看
          </Button>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除项目"
            description="删除后会同步删除该项目下的品牌事实、问题库、内容任务、监测记录和记忆，确定继续吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deletingProjectId === record.id }}
            onConfirm={() => handleDelete(record)}
          >
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
              loading={deletingProjectId === record.id}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>项目管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
          新建项目
        </Button>
      </div>

      <Spin spinning={loading}>
        <Table columns={columns} dataSource={projects} rowKey="id" />
      </Spin>

      <Modal
        title="新建项目"
        open={createModalVisible}
        onOk={() => createForm.submit()}
        onCancel={() => setCreateModalVisible(false)}
        confirmLoading={creating}
        width={640}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <ProjectFormFields />
        </Form>
      </Modal>

      <Modal
        title="编辑项目"
        open={editModalVisible}
        onOk={() => editForm.submit()}
        onCancel={() => {
          setEditModalVisible(false);
          setEditingProject(null);
          editForm.resetFields();
        }}
        confirmLoading={updating}
        width={640}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <ProjectFormFields />
          <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择项目状态' }]}>
            <Select placeholder="选择项目状态">
              {STATUS_OPTIONS.map((item) => (
                <Option key={item.value} value={item.value}>{item.label}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default Projects;
