import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  FileAddOutlined,
  LinkOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { corpusItemsApi, projectsApi } from '../services/api';
import Table from '../components/SafeTable';

const { Option } = Select;
const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const sourceTypeOptions = [
  { value: 'website', label: '官网/网页' },
  { value: 'certificate', label: '资质证书' },
  { value: 'brochure', label: '宣传册/PDF' },
  { value: 'customer_service', label: '客服资料' },
  { value: 'case', label: '案例资料' },
  { value: 'manual', label: '产品/服务手册' },
  { value: 'feedback', label: '客户反馈' },
  { value: 'monitoring', label: '监测复盘' },
  { value: 'other', label: '其他资料' },
];

const knowledgeLayerOptions = [
  { value: 'basic_info', label: '基础信息', color: 'blue' },
  { value: 'story', label: '案例/故事', color: 'purple' },
  { value: 'judgment', label: '判断逻辑', color: 'orange' },
  { value: 'competitor_feedback', label: '竞品/差评', color: 'red' },
  { value: 'content_material', label: '内容素材', color: 'cyan' },
  { value: 'review_data', label: '复盘数据', color: 'green' },
  { value: 'other', label: '其他', color: 'default' },
];

const businessUseOptions = [
  { value: 'fact_extraction', label: '事实提取' },
  { value: 'question_generation', label: '问题生成' },
  { value: 'content_writing', label: '内容写作' },
  { value: 'monitoring_review', label: '监测复盘' },
  { value: 'compliance', label: '合规检查' },
  { value: 'general', label: '通用资料' },
];

const evidenceLevelOptions = [
  { value: 'official', label: '官方资料', color: 'green' },
  { value: 'verified', label: '已核验', color: 'blue' },
  { value: 'user_feedback', label: '用户反馈', color: 'purple' },
  { value: 'internal', label: '内部资料', color: 'orange' },
  { value: 'unverified', label: '待核验', color: 'default' },
];

const reusableScopeOptions = [
  { value: 'project', label: '当前项目', color: 'blue' },
  { value: 'industry', label: '同行业复用', color: 'purple' },
  { value: 'global', label: '全局复用', color: 'green' },
];

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('；');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  return detail || error.message || fallback;
}

function findOption(options, value) {
  return options.find((item) => item.value === value);
}

function renderOptionTag(options, value, fallback = '-') {
  const found = findOption(options, value);
  if (!found) return value || fallback;
  return <Tag color={found.color}>{found.label}</Tag>;
}

function CorpusLibrary() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [ingestModalVisible, setIngestModalVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [claimFilter, setClaimFilter] = useState('all');
  const [knowledgeLayerFilter, setKnowledgeLayerFilter] = useState('all');
  const [businessUseFilter, setBusinessUseFilter] = useState('all');
  const [evidenceLevelFilter, setEvidenceLevelFilter] = useState('all');
  const [form] = Form.useForm();
  const [ingestForm] = Form.useForm();

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const stats = useMemo(() => {
    const countBy = (field, value) => items.filter((item) => item[field] === value).length;
    return {
      total: items.length,
      factual: items.filter((item) => item.contains_factual_claim).length,
      stories: countBy('knowledge_layer', 'story'),
      reviews: countBy('knowledge_layer', 'review_data'),
    };
  }, [items]);

  const loadProjects = async () => {
    try {
      const res = await projectsApi.list({ limit: 100 });
      const data = res.data || [];
      setProjects(data);
      if (!selectedProjectId && data.length) {
        setSelectedProjectId(data[0].id);
      }
    } catch (error) {
      message.error('加载项目失败：' + getErrorMessage(error, '未知错误'));
    }
  };

  const loadItems = async (projectId = selectedProjectId) => {
    if (!projectId) {
      setItems([]);
      return;
    }
    setLoading(true);
    try {
      const params = { project_id: projectId, limit: 500 };
      if (claimFilter !== 'all') {
        params.contains_factual_claim = claimFilter === 'yes';
      }
      if (knowledgeLayerFilter !== 'all') {
        params.knowledge_layer = knowledgeLayerFilter;
      }
      if (businessUseFilter !== 'all') {
        params.business_use = businessUseFilter;
      }
      if (evidenceLevelFilter !== 'all') {
        params.evidence_level = evidenceLevelFilter;
      }
      const res = await corpusItemsApi.list(params);
      setItems(res.data || []);
    } catch (error) {
      message.error('加载项目知识库失败：' + getErrorMessage(error, '未知错误'));
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
      loadItems(selectedProjectId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId, claimFilter, knowledgeLayerFilter, businessUseFilter, evidenceLevelFilter]);

  const openCreateModal = () => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({
      source_type: 'website',
      knowledge_layer: 'basic_info',
      business_use: 'fact_extraction',
      evidence_level: 'unverified',
      reusable_scope: 'project',
      contains_factual_claim: true,
    });
    setModalVisible(true);
  };

  const openIngestModal = () => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    ingestForm.resetFields();
    ingestForm.setFieldsValue({
      source_type: 'brochure',
      max_items: 12,
    });
    setIngestModalVisible(true);
  };

  const openEditModal = (record) => {
    setEditingItem(record);
    form.setFieldsValue({
      title: record.title,
      source_type: record.source_type || 'other',
      source_url: record.source_url,
      tags: record.tags,
      knowledge_layer: record.knowledge_layer || 'basic_info',
      business_use: record.business_use || 'general',
      evidence_level: record.evidence_level || 'unverified',
      reusable_scope: record.reusable_scope || 'project',
      content: record.content,
      contains_factual_claim: Boolean(record.contains_factual_claim),
    });
    setModalVisible(true);
  };

  const handleSave = async (values) => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        project_id: selectedProjectId,
        title: values.title,
        source_type: values.source_type,
        source_url: values.source_url,
        tags: values.tags,
        knowledge_layer: values.knowledge_layer || 'basic_info',
        business_use: values.business_use || 'general',
        evidence_level: values.evidence_level || 'unverified',
        reusable_scope: values.reusable_scope || 'project',
        content: values.content,
        contains_factual_claim: Boolean(values.contains_factual_claim),
      };
      if (editingItem) {
        const { project_id: projectId, ...updatePayload } = payload;
        await corpusItemsApi.update(editingItem.id, updatePayload);
        message.success('项目知识已更新');
      } else {
        await corpusItemsApi.create(payload);
        message.success('项目知识已保存');
      }
      setModalVisible(false);
      setEditingItem(null);
      form.resetFields();
      await loadItems();
    } catch (error) {
      message.error('保存项目知识失败：' + getErrorMessage(error, '未知错误'));
    } finally {
      setSaving(false);
    }
  };

  const handleIngest = async (values) => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    setIngesting(true);
    try {
      const res = await corpusItemsApi.ingest({
        project_id: selectedProjectId,
        title: values.title,
        source_type: values.source_type,
        source_url: values.source_url,
        content: values.content,
        max_items: values.max_items || 12,
      });
      const created = res.data?.created || 0;
      message.success(`AI 已拆分入库 ${created} 条项目知识`);
      setIngestModalVisible(false);
      ingestForm.resetFields();
      await loadItems();
    } catch (error) {
      message.error('AI 分层入库失败：' + getErrorMessage(error, '未知错误'));
    } finally {
      setIngesting(false);
    }
  };

  const handleDelete = async (record) => {
    try {
      await corpusItemsApi.delete(record.id);
      message.success('项目知识已删除');
      await loadItems();
    } catch (error) {
      message.error('删除项目知识失败：' + getErrorMessage(error, '未知错误'));
    }
  };

  const columns = [
    {
      title: '知识标题',
      dataIndex: 'title',
      width: 260,
      render: (value, record) => (
        <Space direction="vertical" size={2}>
          <Text strong>{value || '未命名知识'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.created_at ? new Date(record.created_at).toLocaleString() : '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: '知识层级',
      dataIndex: 'knowledge_layer',
      width: 130,
      render: (value) => renderOptionTag(knowledgeLayerOptions, value),
    },
    {
      title: '业务用途',
      dataIndex: 'business_use',
      width: 130,
      render: (value) => {
        const found = findOption(businessUseOptions, value);
        return found ? found.label : (value || '-');
      },
    },
    {
      title: '证据等级',
      dataIndex: 'evidence_level',
      width: 110,
      render: (value) => renderOptionTag(evidenceLevelOptions, value),
    },
    {
      title: '复用范围',
      dataIndex: 'reusable_scope',
      width: 110,
      render: (value) => renderOptionTag(reusableScopeOptions, value),
    },
    {
      title: '来源类型',
      dataIndex: 'source_type',
      width: 130,
      render: (value) => {
        const found = findOption(sourceTypeOptions, value);
        return found ? found.label : (value || '-');
      },
    },
    {
      title: '事实声明',
      dataIndex: 'contains_factual_claim',
      width: 100,
      render: (value) => (
        value ? <Tag color="green">可提取</Tag> : <Tag>普通资料</Tag>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 180,
      render: (value) => value ? (
        <Space size={4} wrap>
          {String(value).split(/[,，\s]+/).filter(Boolean).slice(0, 6).map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </Space>
      ) : '-',
    },
    {
      title: '知识内容',
      dataIndex: 'content',
      render: (value, record) => (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>
            {value}
          </Paragraph>
          {record.source_url && (
            <a href={record.source_url} target="_blank" rel="noreferrer">
              <LinkOutlined /> 查看来源
            </a>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 170,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openEditModal(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除项目知识"
            description="删除后，这条资料将不再参与事实提取、问题生成和内容写作。已确认的品牌事实不会自动删除。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => handleDelete(record)}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>项目知识库</h1>
          <Text type="secondary">
            统一保存官网、证书、案例、客服话术、客户反馈和监测复盘资料，并标注它们在 GEO 链路里的用途。
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadItems()} disabled={!selectedProjectId}>
            刷新
          </Button>
          <Button icon={<ThunderboltOutlined />} onClick={openIngestModal}>
            AI 分层入库
          </Button>
          <Button type="primary" icon={<FileAddOutlined />} onClick={openCreateModal}>
            新增知识
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="这里是品牌事实库、问题矩阵、文章生成和监测复盘共同使用的资料底座。建议把企业介绍、资质编号、地址电话、价格、案例、用户反馈、竞品信息和检测复盘都先沉淀到这里。"
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="知识总数" value={stats.total} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="可提取事实" value={stats.factual} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="案例/故事" value={stats.stories} suffix="条" />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic title="复盘数据" value={stats.reviews} suffix="条" />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>所属项目</span>
          <Select
            style={{ minWidth: 360 }}
            value={selectedProjectId}
            placeholder="请选择项目"
            onChange={setSelectedProjectId}
          >
            {projects.map((project) => (
              <Option key={project.id} value={project.id}>{project.name}</Option>
            ))}
          </Select>
          <span>资料范围</span>
          <Select style={{ width: 150 }} value={claimFilter} onChange={setClaimFilter}>
            <Option value="all">全部资料</Option>
            <Option value="yes">可提取事实</Option>
            <Option value="no">普通资料</Option>
          </Select>
          <span>知识层级</span>
          <Select style={{ width: 150 }} value={knowledgeLayerFilter} onChange={setKnowledgeLayerFilter}>
            <Option value="all">全部层级</Option>
            {knowledgeLayerOptions.map((item) => (
              <Option key={item.value} value={item.value}>{item.label}</Option>
            ))}
          </Select>
          <span>业务用途</span>
          <Select style={{ width: 150 }} value={businessUseFilter} onChange={setBusinessUseFilter}>
            <Option value="all">全部用途</Option>
            {businessUseOptions.map((item) => (
              <Option key={item.value} value={item.value}>{item.label}</Option>
            ))}
          </Select>
          <span>证据等级</span>
          <Select style={{ width: 150 }} value={evidenceLevelFilter} onChange={setEvidenceLevelFilter}>
            <Option value="all">全部等级</Option>
            {evidenceLevelOptions.map((item) => (
              <Option key={item.value} value={item.value}>{item.label}</Option>
            ))}
          </Select>
          {selectedProject && (
            <Text type="secondary">当前项目：{selectedProject.name}</Text>
          )}
        </Space>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1500 }}
          locale={{ emptyText: selectedProjectId ? '暂无项目知识，请点击“新增知识”录入' : '请先选择项目' }}
        />
      </Card>

      <Modal
        title={editingItem ? '编辑项目知识' : '新增项目知识'}
        open={modalVisible}
        onOk={() => form.submit()}
        onCancel={() => {
          setModalVisible(false);
          setEditingItem(null);
        }}
        confirmLoading={saving}
        okText={editingItem ? '保存修改' : '保存知识'}
        width={900}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item
            name="title"
            label="知识标题"
            rules={[{ required: true, message: '请输入知识标题' }]}
          >
            <Input placeholder="例如：官网企业介绍、CAAC资质证书、产品宣传册、客户案例、监测复盘结论" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="source_type" label="来源类型">
                <Select>
                  {sourceTypeOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="knowledge_layer" label="知识层级" rules={[{ required: true, message: '请选择知识层级' }]}>
                <Select>
                  {knowledgeLayerOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="business_use" label="业务用途" rules={[{ required: true, message: '请选择业务用途' }]}>
                <Select>
                  {businessUseOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="evidence_level" label="证据等级" rules={[{ required: true, message: '请选择证据等级' }]}>
                <Select>
                  {evidenceLevelOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="reusable_scope" label="复用范围" rules={[{ required: true, message: '请选择复用范围' }]}>
                <Select>
                  {reusableScopeOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="contains_factual_claim" label=" " valuePropName="checked">
                <Checkbox>包含可对外核验的事实声明</Checkbox>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tags" label="标签">
                <Input placeholder="例如：资质, 地址, 价格, 案例, 口碑" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source_url" label="来源链接">
                <Input placeholder="可选：官网、新闻稿、平台页面或内部资料链接" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="content"
            label="知识全文"
            rules={[
              { required: true, message: '请粘贴知识全文' },
              { min: 10, message: '知识内容太短' },
            ]}
            extra="可以粘贴长文本。后续 AI 分层入库、事实提取、问题矩阵和文章生成都会优先引用这些结构化知识。"
          >
            <TextArea rows={14} placeholder="把原始企业资料、客户反馈、竞品信息、复盘结论或内容素材粘贴到这里。" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="AI 分层入库"
        open={ingestModalVisible}
        onOk={() => ingestForm.submit()}
        onCancel={() => setIngestModalVisible(false)}
        confirmLoading={ingesting}
        okText="开始分析并入库"
        width={900}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="适合一次性粘贴企业介绍、产品手册、客户案例、竞品资料或监测复盘。AI 会把长资料拆成多条项目知识，并自动标注知识层级、业务用途和证据等级。"
        />
        <Form form={ingestForm} layout="vertical" onFinish={handleIngest}>
          <Form.Item
            name="title"
            label="资料标题"
            rules={[{ required: true, message: '请输入资料标题' }]}
          >
            <Input placeholder="例如：企业完整介绍资料、产品服务手册、客户案例合集" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="source_type" label="来源类型">
                <Select>
                  {sourceTypeOptions.map((item) => (
                    <Option key={item.value} value={item.value}>{item.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="source_url" label="来源链接">
                <Input placeholder="可选：官网、新闻稿或资料页链接" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_items" label="最多拆分条数">
                <InputNumber min={1} max={50} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="content"
            label="原始资料全文"
            rules={[
              { required: true, message: '请粘贴原始资料全文' },
              { min: 10, message: '资料内容太短' },
            ]}
            extra="AI 只负责拆分和标注，不会自动把这些内容变成已确认品牌事实。涉及资质、价格、地址等事实仍建议在品牌事实库里人工确认。"
          >
            <TextArea rows={16} placeholder="把整份资料粘贴到这里，例如企业介绍、证书信息、服务案例、客户反馈、监测复盘结论等。" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default CorpusLibrary;
