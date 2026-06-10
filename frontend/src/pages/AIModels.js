import React, { useEffect, useMemo, useState } from 'react';
import { Card, Button, Tag, Modal, Form, Input, Select, Checkbox, message, Statistic, Row, Col, Spin, Radio, Space, Alert, Typography } from 'antd';
import { PlusOutlined, ThunderboltOutlined, DollarOutlined, ApiOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { aiModelsApi } from '../services/api';
import Table from '../components/SafeTable';

const { Option } = Select;
const { Text } = Typography;

const RECOMMENDED_PROVIDER_KEYS = ['deepseek', 'qwen', 'openai', 'moonshot'];

function AIModels() {
  const [models, setModels] = useState([]);
  const [providers, setProviders] = useState([]);
  const [costSummary, setCostSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [addMode, setAddMode] = useState('preset');
  const [selectedProvider, setSelectedProvider] = useState('deepseek');
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testingModel, setTestingModel] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();

  const loadData = async () => {
    setLoading(true);
    try {
      const [registryRes, providersRes, costRes] = await Promise.all([
        aiModelsApi.listRegistry(),
        aiModelsApi.listProviders(),
        aiModelsApi.getCostSummary(),
      ]);
      setModels(registryRes.data.models || []);
      setProviders(providersRes.data.providers || []);
      setCostSummary(costRes.data);
    } catch (error) {
      message.error('加载模型配置失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const recommendedProviders = useMemo(
    () => providers.filter((provider) => RECOMMENDED_PROVIDER_KEYS.includes(provider.key)),
    [providers],
  );

  const currentProvider = providers.find((provider) => provider.key === selectedProvider);
  const currentProviderModels = currentProvider?.models || [];

  const getProviderName = (key) => {
    const provider = providers.find((item) => item.key === key);
    return provider?.name || key;
  };

  const modelSupportsVision = (record) => (
    record?.supports_vision === true || (record?.tags || []).includes('vision')
  );

  const handleOpenAdd = () => {
    setAddMode('preset');
    setSelectedProvider('deepseek');
    form.resetFields();
    form.setFieldsValue({
      config_mode: 'preset',
      provider: 'deepseek',
      set_as_default: models.length === 0,
      context_length: 64000,
      supports_vision: false,
    });
    setIsModalVisible(true);
  };

  const handleAdd = async (values) => {
    try {
      let payload;
      if (values.config_mode === 'custom') {
        payload = {
          provider: values.custom_provider || 'custom',
          model: values.custom_model,
          api_key: values.api_key,
          name: values.name || `${values.custom_provider || 'Custom'} - ${values.custom_model}`,
          base_url: values.custom_base_url,
          input_price: values.input_price || 0,
          output_price: values.output_price || 0,
          context_length: values.context_length || 4096,
          description: values.description || '自定义 OpenAI 兼容接口',
          supports_vision: Boolean(values.supports_vision),
          set_as_default: values.set_as_default || false,
        };
      } else {
        const providerInfo = providers.find((provider) => provider.key === values.provider);
        const modelInfo = providerInfo?.models?.find((model) => model.id === values.model);
        payload = {
          provider: values.provider,
          model: values.model,
          api_key: values.api_key,
          name: values.name || `${providerInfo?.name || values.provider} - ${modelInfo?.name || values.model}`,
          base_url: values.base_url || providerInfo?.base_url,
          input_price: values.input_price || 0,
          output_price: values.output_price || 0,
          context_length: values.context_length || modelInfo?.context_length || 4096,
          description: values.description || '推荐预设模型',
          supports_vision: Boolean(values.supports_vision),
          set_as_default: values.set_as_default || false,
        };
      }

      await aiModelsApi.addModel(payload);
      setIsModalVisible(false);
      form.resetFields();
      message.success('模型已添加');
      loadData();
    } catch (error) {
      message.error('添加失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleEdit = (record) => {
    setEditingModel(record);
    editForm.setFieldsValue({
      api_key: '',
      base_url: record.base_url || '',
      name: record.name || '',
      input_price: record.input_price_per_1k || 0,
      output_price: record.output_price_per_1k || 0,
      context_length: record.context_length || 4096,
      description: record.description || '',
      supports_vision: modelSupportsVision(record),
      is_active: record.is_active !== false,
    });
    setEditModalVisible(true);
  };

  const handleUpdate = async (values) => {
    if (!editingModel) return;
    try {
      const payload = {};
      if (values.api_key) payload.api_key = values.api_key;
      if (values.base_url !== undefined) payload.base_url = values.base_url || null;
      if (values.name !== undefined) payload.name = values.name;
      if (values.input_price !== undefined) payload.input_price = parseFloat(values.input_price) || 0;
      if (values.output_price !== undefined) payload.output_price = parseFloat(values.output_price) || 0;
      if (values.context_length !== undefined) payload.context_length = parseInt(values.context_length, 10) || 4096;
      if (values.description !== undefined) payload.description = values.description;
      if (values.supports_vision !== undefined) payload.supports_vision = values.supports_vision;
      if (values.is_active !== undefined) payload.is_active = values.is_active;

      await aiModelsApi.updateModel(editingModel.id, payload);
      message.success('模型配置已更新');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingModel(null);
      loadData();
    } catch (error) {
      message.error('更新失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleSetDefault = async (record) => {
    try {
      await aiModelsApi.setDefault(record.id);
      message.success(`已将 ${record.name} 设为默认模型`);
      loadData();
    } catch (error) {
      message.error('设置失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleRemove = async (record) => {
    try {
      await aiModelsApi.removeModel(record.id);
      message.success('模型已删除');
      loadData();
    } catch (error) {
      message.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleTest = (record) => {
    setTestingModel(record);
    setTestResult(null);
    setTestModalVisible(true);
  };

  const runTest = async () => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const res = await aiModelsApi.test({
        model_id: testingModel.id,
        message: '你好，请用一句话回复：连接测试成功。',
      });
      setTestResult({ status: 'success', ...res.data });
      message.success('测试成功');
    } catch (error) {
      setTestResult({
        status: 'error',
        error: error.response?.data?.detail || error.message,
      });
      message.error('测试失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setTestLoading(false);
    }
  };

  const columns = [
    {
      title: '模型',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space direction="vertical" size={2}>
          <Space wrap>
            <Text strong>{text}</Text>
            {record.is_default && <Tag color="blue">默认</Tag>}
            {record.is_custom && <Tag color="purple">自定义</Tag>}
          </Space>
          <Text type="secondary">{record.model}</Text>
        </Space>
      ),
    },
    {
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider) => getProviderName(provider),
    },
    {
      title: '上下文',
      dataIndex: 'context_length',
      key: 'context_length',
      render: (value) => `${Math.round((value || 0) / 1000)}K`,
    },
    {
      title: '能力',
      key: 'capabilities',
      render: (_, record) => (
        <Space wrap>
          {modelSupportsVision(record) ? (
            <Tag color="purple">图片理解</Tag>
          ) : (
            <Tag>文本</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active) => <Tag color={active ? 'green' : 'default'}>{active ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space wrap>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Button type="link" onClick={() => handleTest(record)}>测试</Button>
          {!record.is_default && (
            <Button type="link" onClick={() => handleSetDefault(record)}>设为默认</Button>
          )}
          {record.is_custom && (
            <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleRemove(record)} />
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>AI 模型管理</h2>
          <Text type="secondary">这里只显示已经配置过 API Key 的模型；预设模型只作为添加时的快捷模板。</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenAdd}>添加模型</Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="已配置模型" value={models.length} prefix={<ApiOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="默认模型" value={models.find((model) => model.is_default)?.name || '-'} prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 14 }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日调用成本" value={costSummary?.daily?.cny || 0} prefix={<DollarOutlined />} precision={4} suffix="CNY" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日调用次数" value={costSummary?.daily?.calls || 0} prefix={<ApiOutlined />} />
          </Card>
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Card>
          <Table columns={columns} dataSource={models} rowKey="id" locale={{ emptyText: '还没有配置模型，请点击右上角添加模型' }} />
        </Card>
      </Spin>

      <Modal
        title="添加 AI 模型"
        open={isModalVisible}
        onOk={() => form.submit()}
        onCancel={() => setIsModalVisible(false)}
        width={680}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd} initialValues={{ config_mode: 'preset', provider: 'deepseek', context_length: 64000, supports_vision: false }}>
          <Form.Item name="config_mode" label="配置方式">
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              onChange={(event) => {
                const mode = event.target.value;
                setAddMode(mode);
                if (mode === 'preset') setSelectedProvider('deepseek');
              }}
            >
              <Radio.Button value="preset">推荐预设</Radio.Button>
              <Radio.Button value="custom">自定义接口</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {addMode === 'preset' ? (
            <>
              <Alert message="推荐预设只保留常用入口。选好模型并填 API Key 后，才会出现在已配置列表里。" type="info" showIcon style={{ marginBottom: 16 }} />
              <Form.Item name="provider" label="提供商" rules={[{ required: true }]}>
                <Select
                  onChange={(value) => {
                    setSelectedProvider(value);
                    const providerInfo = providers.find((provider) => provider.key === value);
                    form.setFieldsValue({
                      model: undefined,
                      base_url: '',
                      context_length: providerInfo?.models?.[0]?.context_length || 4096,
                      supports_vision: false,
                    });
                  }}
                >
                  {recommendedProviders.map((provider) => (
                    <Option key={provider.key} value={provider.key}>{provider.name}</Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="model" label="模型" rules={[{ required: true, message: '请选择模型' }]}>
                <Select
                  placeholder="选择模型"
                  onChange={(value) => {
                    const modelInfo = currentProviderModels.find((model) => model.id === value);
                    form.setFieldsValue({
                      context_length: modelInfo?.context_length || 4096,
                      supports_vision: Boolean(modelInfo?.supports_vision),
                    });
                  }}
                >
                  {currentProviderModels.map((model) => (
                    <Option key={model.id} value={model.id}>{model.name} ({model.id})</Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="base_url" label="Base URL">
                <Input placeholder={currentProvider?.base_url || ''} />
              </Form.Item>
            </>
          ) : (
            <>
              <Alert message="用于 OpenAI 兼容接口、转发服务、本地模型网关等。这里完全由你填写，不依赖预设列表。" type="info" showIcon style={{ marginBottom: 16 }} />
              <Form.Item name="custom_provider" label="提供商标识" initialValue="custom" rules={[{ required: true, message: '请输入提供商标识' }]}>
                <Input placeholder="例如：openrouter / ollama / oneapi / custom" />
              </Form.Item>
              <Form.Item name="custom_model" label="模型 ID" rules={[{ required: true, message: '请输入模型 ID' }]}>
                <Input placeholder="例如：gpt-4o / deepseek-chat / qwen-plus / llama3.1" />
              </Form.Item>
              <Form.Item name="custom_base_url" label="Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
                <Input placeholder="例如：https://api.openrouter.ai/v1" />
              </Form.Item>
            </>
          )}

          <Form.Item name="api_key" label="API Key" rules={[{ required: true, message: '请输入 API Key' }]}>
            <Input.Password placeholder="输入 API Key" />
          </Form.Item>
          <Form.Item name="name" label="显示名称">
            <Input placeholder="留空则自动生成" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="input_price" label="输入价格/1K tokens">
                <Input type="number" step={0.001} placeholder="0.0" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="output_price" label="输出价格/1K tokens">
                <Input type="number" step={0.001} placeholder="0.0" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="context_length" label="上下文长度">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="description" label="备注">
            <Input.TextArea rows={2} placeholder="例如：公司统一转发接口、用于文章生成、低成本模型等" />
          </Form.Item>
          <Form.Item
            name="supports_vision"
            valuePropName="checked"
            extra="如果该接口支持图片/截图输入，请勾选。视觉监测会优先使用勾选过的模型。"
          >
            <Checkbox>支持图片理解（可用于视觉识别监测）</Checkbox>
          </Form.Item>
          <Form.Item name="set_as_default" valuePropName="checked">
            <Checkbox>设为默认模型</Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑模型: ${editingModel?.name || ''}`}
        open={editModalVisible}
        onOk={() => editForm.submit()}
        onCancel={() => {
          setEditModalVisible(false);
          setEditingModel(null);
          editForm.resetFields();
        }}
        width={620}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="留空表示不修改" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="例如：https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item name="name" label="显示名称">
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="input_price" label="输入价格/1K tokens">
                <Input type="number" step={0.001} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="output_price" label="输出价格/1K tokens">
                <Input type="number" step={0.001} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="context_length" label="上下文长度">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="description" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="supports_vision"
            valuePropName="checked"
            extra="取消勾选后，该模型不会被视觉识别模式自动选中。"
          >
            <Checkbox>支持图片理解（可用于视觉识别监测）</Checkbox>
          </Form.Item>
          <Form.Item name="is_active" valuePropName="checked">
            <Checkbox>启用该模型</Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`测试模型: ${testingModel?.name || ''}`}
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={[
          <Button key="test" type="primary" onClick={runTest} loading={testLoading}>运行测试</Button>,
          <Button key="close" onClick={() => setTestModalVisible(false)}>关闭</Button>,
        ]}
        width={700}
      >
        <div style={{ marginBottom: 16 }}>
          <p><b>提供商:</b> {getProviderName(testingModel?.provider)} | <b>模型:</b> {testingModel?.model}</p>
          <p>测试会使用该模型保存的 API Key。</p>
        </div>
        {testLoading && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
            <p>正在测试连接...</p>
          </div>
        )}
        {testResult?.status === 'success' && (
          <div>
            <Card title="响应预览" style={{ marginBottom: 16 }}>
              <p style={{ whiteSpace: 'pre-wrap' }}>{testResult.response_preview}</p>
            </Card>
            <Row gutter={16}>
              <Col span={8}><Statistic title="输入 Tokens" value={testResult.usage?.input_tokens || 0} /></Col>
              <Col span={8}><Statistic title="输出 Tokens" value={testResult.usage?.output_tokens || 0} /></Col>
              <Col span={8}><Statistic title="总 Tokens" value={testResult.usage?.total_tokens || 0} /></Col>
            </Row>
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={8}><Statistic title="成本 USD" value={testResult.cost?.usd || 0} precision={6} /></Col>
              <Col span={8}><Statistic title="成本 CNY" value={testResult.cost?.cny || 0} precision={4} /></Col>
              <Col span={8}><Statistic title="延迟 ms" value={testResult.latency_ms || 0} precision={0} /></Col>
            </Row>
          </div>
        )}
        {testResult?.status === 'error' && (
          <Card title="测试失败">
            <p style={{ color: 'red' }}>{testResult.error}</p>
          </Card>
        )}
      </Modal>
    </div>
  );
}

export default AIModels;
