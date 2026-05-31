import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  List,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import { CopyOutlined, DeleteOutlined, EyeOutlined, FileSearchOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import { monitoringApi, projectsApi, reportsApi } from '../services/api';

const { Option } = Select;
const { TextArea } = Input;
const { Paragraph, Text } = Typography;

const confidenceLabels = {
  high: '高',
  medium: '中',
  low: '低',
  very_low: '很低',
};

function Reports() {
  const [projects, setProjects] = useState([]);
  const [runs, setRuns] = useState([]);
  const [report, setReport] = useState(null);
  const [archives, setArchives] = useState([]);
  const [loading, setLoading] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [savingArchive, setSavingArchive] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [lastReportParams, setLastReportParams] = useState(null);
  const [form] = Form.useForm();
  const selectedRunIds = Form.useWatch('run_ids', form) || [];

  const loadProjects = async () => {
    setProjectsLoading(true);
    try {
      const res = await projectsApi.list({ limit: 100 });
      const items = res.data || [];
      setProjects(items);
      if (items.length > 0 && !form.getFieldValue('project_id')) {
        form.setFieldsValue({ project_id: items[0].id });
        loadRuns(items[0].id);
        loadArchives(items[0].id);
      }
    } catch (error) {
      message.error('加载项目失败');
    } finally {
      setProjectsLoading(false);
    }
  };

  const loadArchives = async (projectId) => {
    if (!projectId) {
      setArchives([]);
      return;
    }
    setArchiveLoading(true);
    try {
      const res = await reportsApi.archives({ project_id: projectId, limit: 20 });
      setArchives(res.data || []);
    } catch (error) {
      setArchives([]);
    } finally {
      setArchiveLoading(false);
    }
  };

  const loadRuns = async (projectId) => {
    if (!projectId) {
      setRuns([]);
      return;
    }
    try {
      const res = await monitoringApi.listRuns({ project_id: projectId, limit: 100 });
      setRuns(res.data || []);
    } catch (error) {
      setRuns([]);
    }
  };

  useEffect(() => {
    form.setFieldsValue({
      report_type: 'client',
      time_window_days: 30,
    });
    loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGenerate = async (values) => {
    if (!values.project_id) {
      message.warning('请先选择项目');
      return;
    }
    setLoading(true);
    try {
      const params = {
        project_id: values.project_id,
        report_type: values.report_type || 'client',
        run_ids: values.run_ids,
        run_id: values.run_ids?.length === 1 ? values.run_ids[0] : undefined,
        baseline_run_id: values.run_ids?.length > 1 ? undefined : values.baseline_run_id,
        time_window_days: values.time_window_days || 30,
      };
      const res = await reportsApi.generate(params);
      setReport(res.data);
      setLastReportParams(params);
      message.success('报告已生成');
    } catch (error) {
      message.error('生成报告失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const saveArchive = async () => {
    if (!lastReportParams) {
      message.warning('请先生成一份报告');
      return;
    }
    setSavingArchive(true);
    try {
      const res = await reportsApi.archiveGenerate(lastReportParams);
      setReport(res.data.payload);
      message.success('报告已保存到归档');
      loadArchives(lastReportParams.project_id);
    } catch (error) {
      message.error('保存归档失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingArchive(false);
    }
  };

  const viewArchive = async (archiveId) => {
    setArchiveLoading(true);
    try {
      const res = await reportsApi.archiveDetail(archiveId);
      setReport(res.data.payload);
      setLastReportParams({
        project_id: res.data.project_id,
        report_type: res.data.report_type,
        run_ids: res.data.run_ids || (res.data.run_id ? [res.data.run_id] : []),
        run_id: res.data.run_id,
        baseline_run_id: res.data.baseline_run_id,
        time_window_days: res.data.time_window_days,
      });
      form.setFieldsValue({
        project_id: res.data.project_id,
        report_type: res.data.report_type,
        run_ids: res.data.run_ids || (res.data.run_id ? [res.data.run_id] : []),
        baseline_run_id: res.data.baseline_run_id,
        time_window_days: res.data.time_window_days,
      });
      message.success('已打开归档报告');
    } catch (error) {
      message.error('打开归档失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setArchiveLoading(false);
    }
  };

  const deleteArchive = async (archiveId) => {
    try {
      await reportsApi.deleteArchive(archiveId);
      message.success('归档已删除');
      loadArchives(form.getFieldValue('project_id'));
    } catch (error) {
      message.error('删除归档失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const copyMarkdown = async () => {
    if (!report?.markdown) return;
    try {
      await navigator.clipboard.writeText(report.markdown);
      message.success('Markdown 已复制');
    } catch (error) {
      message.error('复制失败，请手动选中文本复制');
    }
  };

  const metricValue = (value) => (value === null || value === undefined ? '-' : value);

  const renderGuardrails = () => {
    const guardrails = report?.report_guardrails;
    if (!guardrails) return null;
    return (
      <Card title="报告边界">
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text><Text strong>语言口径：</Text>{guardrails.report_language || '-'}</Text>
          <Text><Text strong>引用口径：</Text>{guardrails.citation_policy || '-'}</Text>
          <Text><Text strong>因果口径：</Text>{guardrails.causality_policy || '-'}</Text>
          <Text><Text strong>验收口径：</Text>{guardrails.acceptance_policy || '-'}</Text>
        </Space>
      </Card>
    );
  };

  const renderAcceptanceBaseline = () => {
    const acceptance = report?.acceptance_baseline;
    if (!acceptance) return null;
    const passTag = (pass) => (
      <Tag color={pass ? 'green' : 'orange'}>{pass ? '达标' : '未达标'}</Tag>
    );
    return (
      <Card title="验收基线状态">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            message={acceptance.acceptance_ready ? '当前报告可进入验收复核' : '当前报告仅适合作为阶段观察'}
            description={
              acceptance.acceptance_ready
                ? '当前批次和所选基线均满足样本量与置信等级要求，仍建议人工复核样本文本和关键引用。'
                : '缺少可比基线、样本量不足或置信等级不足时，不建议直接作为交付验收结论。'
            }
            type={acceptance.acceptance_ready ? 'success' : 'warning'}
            showIcon
          />
          <Row gutter={16}>
            <Col xs={24} sm={12} xl={6}>
              <Statistic title="当前样本" value={acceptance.current_sample_count || 0} prefix="N=" />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Statistic title="当前置信" value={confidenceLabels[acceptance.current_confidence_level] || '暂无'} />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Statistic title="基线样本" value={acceptance.baseline_sample_count ?? '-'} prefix={acceptance.baseline_sample_count ? 'N=' : ''} />
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Statistic title="基线置信" value={confidenceLabels[acceptance.baseline_confidence_level] || '暂无'} />
            </Col>
          </Row>
          <Space wrap>
            <Text>当前样本量 {passTag(acceptance.current_sample_size_pass)}</Text>
            <Text>当前置信等级 {passTag(acceptance.current_confidence_pass)}</Text>
            <Text>基线样本量 {passTag(acceptance.baseline_sample_size_pass)}</Text>
            <Text>基线置信等级 {passTag(acceptance.baseline_confidence_pass)}</Text>
          </Space>
          <List
            size="small"
            dataSource={acceptance.notes || []}
            locale={{ emptyText: '暂无补充说明' }}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
        </Space>
      </Card>
    );
  };

  const renderMonitoring = () => {
    const monitoring = report?.monitoring_results || {};
    const metrics = monitoring.metrics || {};
    const mention = metrics.brand_mention_rate || {};
    const recommend = metrics.recommendation_rate || {};
    const explicitRate = metrics.explicit_citation_rate || {};
    const inferredRate = metrics.inferred_source_match_rate || {};
    const sentiment = metrics.sentiment_summary || {};

    if (!monitoring.sample_count) {
      return (
        <Alert
          message="暂无可用于趋势判断的检测样本"
          description={monitoring.message || '报告当前仅展示项目资料、内容和发布进度。'}
          type="info"
          showIcon
        />
      );
    }

    return (
      <Row gutter={16}>
        {monitoring.aggregation_mode === 'multi_run' && (
          <Col span={24} style={{ marginBottom: 12 }}>
            <Alert
              type="info"
              showIcon
              message={`当前报告已聚合 ${monitoring.selected_run_count || monitoring.run_ids?.length || 0} 组检测记录`}
              description={(monitoring.run_summaries || [])
                .map((run) => `${run.model_target_name || run.mechanism_type || '检测'}：${run.sample_count || 0}样本`)
                .join('；')}
            />
          </Col>
        )}
        <Col xs={24} sm={12} xl={6}>
          <Statistic title="样本数" value={monitoring.sample_count} prefix="N=" />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Statistic title="品牌提及率" value={mention.point_estimate} suffix="%" />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Statistic title="推荐率" value={recommend.point_estimate} suffix="%" />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Statistic title="置信等级" value={confidenceLabels[monitoring.confidence_level] || '暂无'} />
        </Col>
        <Col span={24} style={{ marginTop: 12 }}>
          <Text type="secondary">
            品牌提及率 95% CI：{metricValue(mention.lower)}% ~ {metricValue(mention.upper)}%；
            推荐率 95% CI：{metricValue(recommend.lower)}% ~ {metricValue(recommend.upper)}%；
            显式引用 {metrics.total_explicit_citations || 0} 次（引用率 {metricValue(explicitRate.point_estimate)}%），
            推断来源匹配 {metrics.total_inferred_source_matches || 0} 次（匹配率 {metricValue(inferredRate.point_estimate)}%）；
            未关闭舆情/风险 {sentiment.open_records || 0} 条，负面样本 {sentiment.negative_samples || 0} 个。
          </Text>
        </Col>
      </Row>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>报告中心</h2>
        <Button icon={<ReloadOutlined />} onClick={loadProjects}>
          刷新
        </Button>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Spin spinning={projectsLoading}>
          <Form form={form} layout="inline" onFinish={handleGenerate}>
            <Form.Item name="project_id" label="项目" rules={[{ required: true, message: '请选择项目' }]}>
              <Select
                style={{ width: 280 }}
                placeholder="选择项目"
                onChange={(projectId) => {
                  form.setFieldsValue({ run_ids: undefined, run_id: undefined, baseline_run_id: undefined });
                  loadRuns(projectId);
                  loadArchives(projectId);
                }}
              >
                {projects.map((project) => (
                  <Option key={project.id} value={project.id}>{project.name}</Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="report_type" label="报告类型">
              <Radio.Group>
                <Radio.Button value="client">客户报告</Radio.Button>
                <Radio.Button value="internal">内部报告</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item name="run_ids" label="检测记录">
              <Select
                allowClear
                mode="multiple"
                maxTagCount="responsive"
                style={{ minWidth: 320 }}
                placeholder="可多选；不选则默认使用最新检测"
                onChange={(ids) => {
                  if ((ids || []).length > 1) {
                    form.setFieldsValue({ baseline_run_id: undefined });
                  }
                }}
              >
                {runs.map((run) => (
                  <Option key={run.id} value={run.id}>
                    {`${run.model_target_name || run.mechanism_type || '检测'} / ${run.sample_count || 0}样本 / ${run.status}`}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="baseline_run_id" label="对比基线">
              <Select
                allowClear
                disabled={selectedRunIds.length > 1}
                style={{ width: 220 }}
                placeholder={selectedRunIds.length > 1 ? '聚合报告暂不支持基线对比' : '选择基线任务'}
              >
                {runs.map((run) => (
                  <Option key={run.id} value={run.id}>
                    {`${run.run_type === 'baseline' ? '基线' : run.run_type} / ${run.model_target_name || run.mechanism_type || '-'} / ${run.sample_count || 0}样本`}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="time_window_days" label="观察周期">
              <Select style={{ width: 110 }}>
                <Option value={7}>7天</Option>
                <Option value={30}>30天</Option>
                <Option value={60}>60天</Option>
                <Option value={90}>90天</Option>
              </Select>
            </Form.Item>
            <Form.Item>
              <Button type="primary" icon={<FileSearchOutlined />} loading={loading} htmlType="submit">
                生成报告
              </Button>
            </Form.Item>
            <Form.Item>
              <Button icon={<SaveOutlined />} loading={savingArchive} onClick={saveArchive} disabled={!report}>
                保存归档
              </Button>
            </Form.Item>
          </Form>
        </Spin>
      </Card>

      <Card title="报告归档" style={{ marginBottom: 16 }}>
        <List
          loading={archiveLoading}
          dataSource={archives}
          locale={{ emptyText: '暂无归档报告' }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key="view" type="link" icon={<EyeOutlined />} onClick={() => viewArchive(item.id)}>
                  查看
                </Button>,
                <Popconfirm
                  key="delete"
                  title="确认删除这份归档报告？"
                  okText="删除"
                  cancelText="取消"
                  onConfirm={() => deleteArchive(item.id)}
                >
                  <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Text strong>{item.title}</Text>
                    <Tag color={item.report_type === 'client' ? 'blue' : 'purple'}>
                      {item.report_type === 'client' ? '客户报告' : '内部报告'}
                    </Tag>
                    <Tag color={item.acceptance_ready ? 'green' : 'orange'}>
                      {item.acceptance_ready ? '可验收复核' : '阶段观察'}
                    </Tag>
                  </Space>
                }
                description={`N=${item.sample_count || 0} / 置信等级：${confidenceLabels[item.confidence_level] || '暂无'} / ${item.created_at || '-'}`}
              />
            </List.Item>
          )}
        />
      </Card>

      <Spin spinning={loading}>
        {!report ? (
          <Empty description="请选择项目后生成报告" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              message={report.report_type === 'client' ? '客户报告' : '内部报告'}
              description={report.disclaimer}
              type={report.report_type === 'client' ? 'success' : 'warning'}
              showIcon
            />

            {renderGuardrails()}

            <Row gutter={16}>
              <Col xs={24} sm={12} xl={6}>
                <Card>
                  <Statistic title="已确认公开事实" value={report.key_metrics.confirmed_public_facts} suffix="条" />
                </Card>
              </Col>
              <Col xs={24} sm={12} xl={6}>
                <Card>
                  <Statistic title="有效信源资产" value={report.key_metrics.active_source_assets || 0} suffix="个" />
                </Card>
              </Col>
              <Col xs={24} sm={12} xl={6}>
                <Card>
                  <Statistic title="有效问题组" value={report.key_metrics.question_groups} suffix="个" />
                </Card>
              </Col>
              <Col xs={24} sm={12} xl={6}>
                <Card>
                  <Statistic title="已发布内容" value={report.key_metrics.content_published} suffix="条" />
                </Card>
              </Col>
            </Row>

            <Card title="阶段摘要">
              <Paragraph>{report.executive_summary}</Paragraph>
            </Card>

            <Card title="检测观察">
              {renderMonitoring()}
            </Card>

            {renderAcceptanceBaseline()}

            {report.baseline_comparison?.comparison && (
              <Card title="基线对比">
                <Row gutter={16}>
                  <Col xs={24} sm={8}>
                    <Statistic title="品牌提及率变化" value={report.baseline_comparison.comparison.mention_delta} suffix="百分点" />
                  </Col>
                  <Col xs={24} sm={8}>
                    <Statistic title="推荐率变化" value={report.baseline_comparison.comparison.recommend_delta} suffix="百分点" />
                  </Col>
                  <Col xs={24} sm={8}>
                    <Statistic
                      title="内部显著变化"
                      value={report.baseline_comparison.comparison.significant_change ? '是' : '否'}
                    />
                  </Col>
                </Row>
              </Card>
            )}

            <Card title="已发布内容">
              <List
                dataSource={report.published_content || []}
                locale={{ emptyText: '暂无发布记录' }}
                renderItem={(item) => (
                  <List.Item>
                    <Space direction="vertical" size={2}>
                      <Space>
                        <Text strong>{item.title || '未命名内容'}</Text>
                        <Tag>{item.platform}</Tag>
                        {item.is_indexed && <Tag color="green">已收录</Tag>}
                      </Space>
                      {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a> : <Text type="secondary">暂无链接</Text>}
                    </Space>
                  </List.Item>
                )}
              />
            </Card>

            <Card title="下一步建议">
              <List
                dataSource={report.next_steps || []}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Card>

            {report.internal_findings && (
              <Card title="内部执行判断">
                <Text strong>执行缺口</Text>
                <List
                  size="small"
                  dataSource={report.internal_findings.execution_gaps || []}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
                <Divider />
                <Text strong>风险提示</Text>
                <List
                  size="small"
                  dataSource={report.internal_findings.risks || []}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </Card>
            )}

            <Card
              title="Markdown 报告"
              extra={
                <Space wrap>
                  <Button icon={<SaveOutlined />} loading={savingArchive} onClick={saveArchive}>保存归档</Button>
                  <Button icon={<CopyOutlined />} onClick={copyMarkdown}>复制 Markdown</Button>
                </Space>
              }
            >
              <TextArea rows={18} value={report.markdown || ''} readOnly />
            </Card>
          </Space>
        )}
      </Spin>
    </div>
  );
}

export default Reports;
