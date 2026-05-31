import React, { useState, useEffect } from 'react';
import { Alert, Card, Button, Tag, Modal, Form, Input, Select, Radio, message, Spin, List, Typography, Space, Badge, InputNumber, Popconfirm } from 'antd';
import {
  PlusOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ImportOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { brandFactsApi, brandsApi, corpusItemsApi, projectsApi } from '../services/api';
import Table from '../components/SafeTable';

const { Option } = Select;
const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const factTypeLabels = {
  qualification: '资质',
  address: '地址',
  phone: '电话',
  price: '价格',
  case_study: '案例',
  contact: '联系方式',
  founding_date: '成立时间',
  product: '产品',
  service: '服务',
  certification: '证书',
};

function BrandFacts() {
  const [facts, setFacts] = useState([]);
  const [projects, setProjects] = useState([]);
  const [brands, setBrands] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedBrandId, setSelectedBrandId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [confirmModalVisible, setConfirmModalVisible] = useState(false);
  const [confirmingFact, setConfirmingFact] = useState(null);
  const [bulkExtractVisible, setBulkExtractVisible] = useState(false);
  const [bulkExtracting, setBulkExtracting] = useState(false);
  const [selectedFactIds, setSelectedFactIds] = useState([]);
  const [batchConfirming, setBatchConfirming] = useState(false);
  const [extractModalVisible, setExtractModalVisible] = useState(false);
  const [corpusItems, setCorpusItems] = useState([]);
  const [corpusLoading, setCorpusLoading] = useState(false);
  const [selectedCorpus, setSelectedCorpus] = useState(null);
  const [historyModalVisible, setHistoryModalVisible] = useState(false);
  const [historyFact, setHistoryFact] = useState(null);
  const [historyEvents, setHistoryEvents] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingFact, setEditingFact] = useState(null);
  const [bulkExtractForm] = Form.useForm();
  const [extractForm] = Form.useForm();
  const [confirmForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [form] = Form.useForm();

  const loadProjects = async () => {
    try {
      const res = await projectsApi.list({ limit: 100 });
      const items = res.data || [];
      setProjects(items);
      if (items.length > 0 && !selectedProjectId) {
        const projectId = items[0].id;
        setSelectedProjectId(projectId);
        await loadBrands(projectId);
        await loadFacts(projectId);
      }
    } catch (error) {
      message.error('加载项目失败');
    }
  };

  const loadBrands = async (projectId) => {
    if (!projectId) {
      setBrands([]);
      setSelectedBrandId(null);
      return;
    }
    try {
      const res = await projectsApi.getBrands(projectId);
      const items = res.data || [];
      setBrands(items);
      setSelectedBrandId(items[0]?.id || null);
    } catch (error) {
      setBrands([]);
      setSelectedBrandId(null);
      message.error('加载品牌主体失败');
    }
  };

  const handleProjectChange = async (projectId) => {
    setSelectedProjectId(projectId);
    await loadBrands(projectId);
    await loadFacts(projectId);
  };

  const createDefaultBrand = async () => {
    const project = projects.find((item) => item.id === selectedProjectId);
    if (!project) {
      message.warning('请先选择项目');
      return null;
    }
    const res = await brandsApi.create({
      project_id: project.id,
      brand_name: project.name,
      company_name: project.name,
      description: project.notes || '',
    });
    const brand = res.data;
    setBrands([brand, ...brands]);
    setSelectedBrandId(brand.id);
    message.success('已创建默认品牌主体');
    return brand;
  };

  const loadFacts = async (projectId = selectedProjectId) => {
    setLoading(true);
    try {
      const params = projectId ? { project_id: projectId, limit: 100 } : { limit: 100 };
      const res = await brandFactsApi.list(params);
      setFacts(res.data || []);
      setSelectedFactIds([]);
    } catch (error) {
      message.error('加载品牌事实失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openExtractModal = async () => {
    setExtractModalVisible(true);
    setCorpusLoading(true);
    try {
      const res = await corpusItemsApi.list({ contains_factual_claim: true, limit: 100 });
      setCorpusItems(res.data || []);
    } catch (error) {
      message.error('加载语料库失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCorpusLoading(false);
    }
  };

  const handleBulkExtract = async (values) => {
    let brandId = selectedBrandId;
    if (!brandId) {
      const brand = await createDefaultBrand();
      brandId = brand?.id;
    }
    if (!brandId) {
      message.warning('请先选择或创建品牌主体');
      return;
    }

    setBulkExtracting(true);
    try {
      const res = await brandFactsApi.extractFromText({
        brand_id: brandId,
        content: values.content,
        source: values.source || '企业资料粘贴文本',
        max_facts: Number(values.max_facts || 24),
      });
      const count = Array.isArray(res.data) ? res.data.length : 0;
      message.success(`AI 已提取 ${count} 条品牌事实候选，请确认后用于内容生成`);
      setBulkExtractVisible(false);
      bulkExtractForm.resetFields();
      await loadFacts();
    } catch (error) {
      message.error('AI 批量提取失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setBulkExtracting(false);
    }
  };

  const handleBatchConfirm = async () => {
    const selectedFacts = facts.filter((fact) => selectedFactIds.includes(fact.id) && fact.status !== 'confirmed');
    if (!selectedFacts.length) {
      message.warning('请选择待确认的事实');
      return;
    }
    setBatchConfirming(true);
    try {
      await Promise.all(selectedFacts.map((fact) => (
        brandFactsApi.confirm(
          fact.id,
          fact.public_wording || undefined
        )
      )));
      message.success(`已确认 ${selectedFacts.length} 条品牌事实`);
      setSelectedFactIds([]);
      loadFacts();
    } catch (error) {
      message.error('批量确认失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setBatchConfirming(false);
    }
  };

  const handleSelectCorpus = (item) => {
    setSelectedCorpus(item);
    // 预填充提取表单：从内容中简单识别可能的事实类型
    const content = item.content || '';
    const detectedType = content.includes('资质') || content.includes('证书')
      ? 'qualification'
      : content.includes('地址') || content.includes('位于')
      ? 'address'
      : content.includes('电话') || content.includes('联系')
      ? 'contact'
      : content.includes('价格') || content.includes('费用') || content.includes('元')
      ? 'price'
      : content.includes('案例') || content.includes('客户')
      ? 'case_study'
      : 'product';

    extractForm.setFieldsValue({
      fact_type: detectedType,
      value: content.slice(0, 500),
      public_wording: '',
      fact_scope: 'public',
      risk_level: 'low',
    });
  };

  const handleExtract = async (values) => {
    if (!selectedCorpus) {
      message.warning('请先选择一条语料');
      return;
    }
    let brandId = selectedBrandId;
    if (!brandId) {
      const brand = await createDefaultBrand();
      brandId = brand?.id;
    }
    if (!brandId) {
      message.warning('请先选择或创建品牌主体');
      return;
    }
    try {
      await brandFactsApi.extractFromCorpus(selectedCorpus.id, [
        {
          brand_id: brandId,
          fact_type: values.fact_type,
          value: values.value,
          public_wording: values.public_wording,
          fact_scope: values.fact_scope,
          internal_note: `从语料提取: ${selectedCorpus.title || selectedCorpus.id}`,
        },
      ]);
      message.success('事实候选已提取，等待确认');
      setExtractModalVisible(false);
      setSelectedCorpus(null);
      extractForm.resetFields();
      loadFacts();
    } catch (error) {
      message.error('提取失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openConfirm = (record) => {
    setConfirmingFact(record);
    confirmForm.setFieldsValue({
      public_wording: record.public_wording || '',
      evidence_file_url: record.evidence_file_url || '',
      evidence_type: record.evidence_type || '',
      confirmation_note: '',
    });
    setConfirmModalVisible(true);
  };

  const handleConfirm = async (values) => {
    try {
      await brandFactsApi.confirmWithEvidence(confirmingFact.id, values);
      message.success('事实已确认');
      setConfirmModalVisible(false);
      loadFacts();
    } catch (error) {
      message.error('确认失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openHistory = async (record) => {
    setHistoryFact(record);
    setHistoryModalVisible(true);
    setHistoryLoading(true);
    try {
      const res = await brandFactsApi.history(record.id, { limit: 100 });
      setHistoryEvents(res.data || []);
    } catch (error) {
      message.error('加载事实历史失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setHistoryLoading(false);
    }
  };

  const openEdit = (record) => {
    setEditingFact(record);
    editForm.setFieldsValue({
      value: record.value,
      public_wording: record.public_wording,
      source: record.source,
      evidence_file_url: record.evidence_file_url,
      evidence_type: record.evidence_type,
      fact_scope: record.fact_scope,
      risk_level: record.risk_level,
      internal_note: record.internal_note,
    });
    setEditModalVisible(true);
  };

  const handleEdit = async (values) => {
    try {
      await brandFactsApi.update(editingFact.id, values);
      message.success('事实已更新，并已记录变更历史');
      setEditModalVisible(false);
      setEditingFact(null);
      loadFacts();
    } catch (error) {
      message.error('更新事实失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleAdd = async (values) => {
    let brandId = selectedBrandId;
    if (!brandId) {
      const brand = await createDefaultBrand();
      brandId = brand?.id;
    }
    if (!brandId) {
      message.warning('请先选择或创建品牌主体');
      return;
    }
    try {
      await brandFactsApi.create({
        ...values,
        brand_id: brandId,
      });
      message.success('事实候选已创建，等待确认');
      setIsModalVisible(false);
      form.resetFields();
      loadFacts();
    } catch (error) {
      message.error('添加失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const columns = [
    {
      title: '事实类型',
      dataIndex: 'fact_type',
      key: 'fact_type',
      render: (t) => factTypeLabels[t] || t,
    },
    { title: '值', dataIndex: 'value', key: 'value', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s) => (
        <Tag
          icon={s === 'confirmed' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
          color={s === 'confirmed' ? 'green' : s === 'draft' ? 'orange' : s === 'disputed' ? 'red' : 'default'}
        >
          {s === 'confirmed' ? '已确认' : s === 'draft' ? '待确认' : s === 'disputed' ? '争议中' : s}
        </Tag>
      ),
    },
    {
      title: '公开范围',
      dataIndex: 'fact_scope',
      key: 'fact_scope',
      render: (s) => (
        <Tag color={s === 'public' ? 'blue' : s === 'internal' ? 'orange' : 'red'}>
          {s === 'public' ? '公开' : s === 'internal' ? '内部' : '受限'}
        </Tag>
      ),
    },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      render: (r) => (
        <Tag color={r === 'high' ? 'red' : r === 'medium' ? 'orange' : 'green'}>
          {r === 'high' ? '高' : r === 'medium' ? '中' : '低'}
        </Tag>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      ellipsis: true,
      render: (s) => s || '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" onClick={() => openEdit(record)}>编辑</Button>
          <Button type="link" onClick={() => openHistory(record)}>历史</Button>
          <Button type="link" disabled={record.status === 'confirmed'} onClick={() => openConfirm(record)}>
          {record.status === 'confirmed' ? '已确认' : '确认'}
          </Button>
        </Space>
      ),
    },
  ];

  const selectedConfirmableCount = facts.filter(
    (fact) => selectedFactIds.includes(fact.id) && fact.status !== 'confirmed'
  ).length;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 12 }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>品牌事实库</h2>
            <Text type="secondary">先把企业资料一次性给 AI 分析，生成事实候选；确认后才会进入问题库、文章和报告链路。</Text>
          </div>
          <Button type="primary" icon={<RobotOutlined />} size="large" onClick={() => setBulkExtractVisible(true)}>
            AI 批量提取企业资料
          </Button>
        </div>

        <Card size="small">
          <Space wrap>
            <Select
              style={{ width: 260 }}
              placeholder="选择项目"
              value={selectedProjectId}
              onChange={handleProjectChange}
            >
              {projects.map((project) => (
                <Option key={project.id} value={project.id}>{project.name}</Option>
              ))}
            </Select>
            <Select
              style={{ width: 220 }}
              placeholder="选择品牌主体"
              value={selectedBrandId}
              onChange={setSelectedBrandId}
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <div style={{ padding: 8 }}>
                    <Button type="link" size="small" onClick={createDefaultBrand}>
                      创建默认品牌主体
                    </Button>
                  </div>
                </>
              )}
            >
              {brands.map((brand) => (
                <Option key={brand.id} value={brand.id}>{brand.brand_name}</Option>
              ))}
            </Select>
            <Popconfirm
              title="批量确认事实"
              description="确认后这些事实会作为公开事实参与文章生成，请确认内容准确。"
              okText="确认"
              cancelText="取消"
              onConfirm={handleBatchConfirm}
              disabled={!selectedConfirmableCount}
            >
              <Button
                icon={<CheckCircleOutlined />}
                loading={batchConfirming}
                disabled={!selectedConfirmableCount}
              >
                批量确认选中{selectedConfirmableCount ? ` (${selectedConfirmableCount})` : ''}
              </Button>
            </Popconfirm>
            <Button icon={<ImportOutlined />} onClick={openExtractModal}>
              从语料提取
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>
              手动添加事实
            </Button>
          </Space>
        </Card>
      </div>

      <Spin spinning={loading}>
        <Card>
          <Table
            columns={columns}
            dataSource={facts}
            rowKey="id"
            rowSelection={{
              selectedRowKeys: selectedFactIds,
              onChange: setSelectedFactIds,
              getCheckboxProps: (record) => ({ disabled: record.status === 'confirmed' }),
            }}
          />
        </Card>
      </Spin>

      {/* AI批量提取企业资料Modal */}
      <Modal
        title="AI 批量提取企业资料"
        open={bulkExtractVisible}
        onOk={() => bulkExtractForm.submit()}
        onCancel={() => setBulkExtractVisible(false)}
        confirmLoading={bulkExtracting}
        okText="开始提取"
        width={860}
      >
        <Alert
          message="把企业介绍、产品资料、资质证书、编号、地址电话、价格、案例等一次性粘贴进来。AI 会拆成待确认事实候选，不会直接发布使用。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form
          form={bulkExtractForm}
          layout="vertical"
          onFinish={handleBulkExtract}
          initialValues={{ source: '企业资料粘贴文本', max_facts: 24 }}
        >
          <Form.Item name="source" label="资料来源">
            <Input placeholder="例如：官网介绍、营业执照、资质证书PDF、企业宣传册、客服资料" />
          </Form.Item>
          <Form.Item
            name="content"
            label="企业资料全文"
            rules={[
              { required: true, message: '请粘贴企业资料' },
              { min: 20, message: '资料内容太短，无法提取有效事实' },
            ]}
          >
            <TextArea
              rows={14}
              placeholder="把企业资料整体粘贴到这里。示例：公司名称、主营业务、培训资质、证书编号、课程内容、价格、地址、联系电话、通过率、学员案例、官网/公众号信息等。"
            />
          </Form.Item>
          <Form.Item name="max_facts" label="最多提取条数">
            <InputNumber min={1} max={50} style={{ width: 180 }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加事实Modal */}
      <Modal title="添加品牌事实" open={isModalVisible} onOk={() => form.submit()} onCancel={() => setIsModalVisible(false)} width={600}>
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item name="fact_type" label="事实类型" rules={[{ required: true }]}>
            <Select placeholder="选择事实类型">
              {Object.entries(factTypeLabels).map(([key, label]) => (
                <Option key={key} value={key}>{label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="value" label="值" rules={[{ required: true }]}>
            <TextArea rows={2} placeholder="输入事实内容" />
          </Form.Item>
          <Form.Item name="public_wording" label="公开口径">
            <TextArea rows={2} placeholder="对外公开使用的表述（可选）" />
          </Form.Item>
          <Form.Item name="fact_scope" label="公开范围" initialValue="public">
            <Radio.Group>
              <Radio value="public">公开</Radio>
              <Radio value="internal">内部</Radio>
              <Radio value="restricted">受限</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="source" label="来源">
            <Input placeholder="信息来源" />
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级" initialValue="low">
            <Radio.Group>
              <Radio value="low">低</Radio>
              <Radio value="medium">中</Radio>
              <Radio value="high">高</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* 确认事实Modal */}
      <Modal
        title={`确认事实: ${confirmingFact ? (factTypeLabels[confirmingFact.fact_type] || confirmingFact.fact_type) : ''}`}
        open={confirmModalVisible}
        onOk={() => confirmForm.submit()}
        onCancel={() => setConfirmModalVisible(false)}
      >
        <p>
          <b>当前值:</b> {confirmingFact?.value}
        </p>
        <Form form={confirmForm} layout="vertical" onFinish={handleConfirm}>
          <Form.Item name="public_wording" label="公开口径">
            <TextArea rows={3} placeholder="对外公开使用的表述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 从语料提取Modal */}
      <Modal
        title="从语料库提取事实"
        open={editModalVisible}
        onOk={() => editForm.submit()}
        onCancel={() => setEditModalVisible(false)}
        width={720}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="value" label="事实内容" rules={[{ required: true }]}>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="public_wording" label="公开口径">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="source" label="来源">
            <Input />
          </Form.Item>
          <Form.Item name="evidence_file_url" label="证据链接/文件">
            <Input />
          </Form.Item>
          <Form.Item name="evidence_type" label="证据类型">
            <Input placeholder="certificate / official_page / contract / manual" />
          </Form.Item>
          <Form.Item name="fact_scope" label="公开范围">
            <Radio.Group>
              <Radio value="public">公开</Radio>
              <Radio value="internal">内部</Radio>
              <Radio value="restricted">受限</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="risk_level" label="风险等级">
            <Radio.Group>
              <Radio value="low">低</Radio>
              <Radio value="medium">中</Radio>
              <Radio value="high">高</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="internal_note" label="内部备注">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`事实历史: ${historyFact ? (factTypeLabels[historyFact.fact_type] || historyFact.fact_type) : ''}`}
        open={historyModalVisible}
        onCancel={() => setHistoryModalVisible(false)}
        footer={null}
        width={860}
      >
        <Spin spinning={historyLoading}>
          <List
            dataSource={historyEvents}
            locale={{ emptyText: '暂无历史记录' }}
            renderItem={(event) => {
              const after = event.snapshot?.after || event.snapshot || {};
              const before = event.snapshot?.before || {};
              return (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Tag color="blue">{event.action}</Tag>
                        <Text>{event.previous_status || '-'} → {event.new_status || '-'}</Text>
                        <Text type="secondary">{event.created_at ? new Date(event.created_at).toLocaleString() : '-'}</Text>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        {event.actor_id && <Text type="secondary">操作人: {event.actor_id}</Text>}
                        {event.note && <Text>说明: {event.note}</Text>}
                        {after.public_wording && <Text>公开口径: {after.public_wording}</Text>}
                        {after.evidence_type && <Text>证据类型: {after.evidence_type}</Text>}
                        {after.evidence_file_url && <Text>证据: {after.evidence_file_url}</Text>}
                        {before.value && before.value !== after.value && (
                          <Text type="secondary">变更前: {before.value}</Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              );
            }}
          />
        </Spin>
      </Modal>

      <Modal
        title="从语料库提取事实"
        open={extractModalVisible}
        onCancel={() => {
          setExtractModalVisible(false);
          setSelectedCorpus(null);
          extractForm.resetFields();
        }}
        width={800}
        footer={null}
      >
        <Spin spinning={corpusLoading}>
          {!selectedCorpus ? (
            <div>
              <Paragraph type="secondary">
                选择一条标记为"含事实声明"的语料，系统将基于其内容生成事实候选（draft状态，需客户确认）。
              </Paragraph>
              <List
                size="small"
                bordered
                dataSource={corpusItems}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button type="link" size="small" onClick={() => handleSelectCorpus(item)}>
                        选择提取
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text strong>{item.title || '未命名语料'}</Text>
                          {item.contains_factual_claim && (
                            <Badge color="red" text="含事实声明" />
                          )}
                        </Space>
                      }
                      description={
                        <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>
                          {item.content}
                        </Paragraph>
                      }
                    />
                  </List.Item>
                )}
                locale={{ emptyText: '暂无含事实声明的语料，请先在语料库中录入内容并标记 contains_factual_claim=true' }}
              />
            </div>
          ) : (
            <div>
              <Card size="small" style={{ marginBottom: 16 }}>
                <Paragraph type="secondary">来源语料</Paragraph>
                <Text strong>{selectedCorpus.title || '未命名语料'}</Text>
                <Paragraph ellipsis={{ rows: 3 }} style={{ marginTop: 8 }}>
                  {selectedCorpus.content}
                </Paragraph>
                <Button type="link" size="small" onClick={() => setSelectedCorpus(null)}>
                  ← 重新选择语料
                </Button>
              </Card>

              <Form form={extractForm} layout="vertical" onFinish={handleExtract}>
                <Form.Item name="brand_id" label="品牌ID" hidden initialValue="00000000-0000-0000-0000-000000000000">
                  <Input />
                </Form.Item>
                <Form.Item name="fact_type" label="事实类型" rules={[{ required: true }]}>
                  <Select placeholder="选择事实类型">
                    {Object.entries(factTypeLabels).map(([key, label]) => (
                      <Option key={key} value={key}>{label}</Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item name="value" label="事实值" rules={[{ required: true }]}>
                  <TextArea rows={3} placeholder="从语料中提取的事实内容" />
                </Form.Item>
                <Form.Item name="public_wording" label="公开口径">
                  <TextArea rows={2} placeholder="对外公开使用的表述（可选）" />
                </Form.Item>
                <Form.Item name="fact_scope" label="公开范围" initialValue="public">
                  <Radio.Group>
                    <Radio value="public">公开</Radio>
                    <Radio value="internal">内部</Radio>
                    <Radio value="restricted">受限</Radio>
                  </Radio.Group>
                </Form.Item>
                <Form.Item name="risk_level" label="风险等级" initialValue="low">
                  <Radio.Group>
                    <Radio value="low">低</Radio>
                    <Radio value="medium">中</Radio>
                    <Radio value="high">高</Radio>
                  </Radio.Group>
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit">
                    提取为事实候选
                  </Button>
                </Form.Item>
              </Form>
            </div>
          )}
        </Spin>
      </Modal>
    </div>
  );
}

export default BrandFacts;
