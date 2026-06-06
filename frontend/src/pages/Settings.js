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

import { platformPoliciesApi, questionArchetypesApi, usersApi } from '../services/api';

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
  const [questionArchetypes, setQuestionArchetypes] = useState([]);
  const [templateSuggestions, setTemplateSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [archetypeLoading, setArchetypeLoading] = useState(false);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState(null);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState(null);
  const [archetypeModalOpen, setArchetypeModalOpen] = useState(false);
  const [editingArchetype, setEditingArchetype] = useState(null);
  const [form] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [policyForm] = Form.useForm();
  const [archetypeForm] = Form.useForm();
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
      message.error('鍔犺浇鐢ㄦ埛澶辫触: ' + (error.response?.data?.detail || error.message));
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
      message.error('鍔犺浇骞冲彴瑙勫垯澶辫触: ' + (error.response?.data?.detail || error.message));
    } finally {
      setPolicyLoading(false);
    }
  };

  const loadQuestionArchetypes = async () => {
    if (!isAdmin) return;
    setArchetypeLoading(true);
    try {
      const res = await questionArchetypesApi.list();
      setQuestionArchetypes(res.data?.industries || []);
    } catch (error) {
      message.error('鍔犺浇琛屼笟闂妯℃澘澶辫触: ' + (error.response?.data?.detail || error.message));
    } finally {
      setArchetypeLoading(false);
    }
  };

  const loadQuestionLearningSuggestions = async () => {
    if (!isAdmin) return;
    setSuggestionLoading(true);
    try {
      const res = await questionArchetypesApi.suggestions({ limit: 200 });
      setTemplateSuggestions(res.data?.items || []);
    } catch (error) {
      message.error('鍔犺浇妯℃澘浼樺寲寤鸿澶辫触: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSuggestionLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    loadPlatformPolicies();
    loadQuestionArchetypes();
    loadQuestionLearningSuggestions();
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
        message.success('鐢ㄦ埛宸叉洿鏂?);
      } else {
        await usersApi.create(values);
        message.success('鐢ㄦ埛宸插垱寤?);
      }
      setUserModalOpen(false);
      await loadUsers();
    } catch (error) {
      message.error('淇濆瓨鐢ㄦ埛澶辫触: ' + (error.response?.data?.detail || error.message));
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
      message.success('瀵嗙爜宸查噸缃?);
      setPasswordModalOpen(false);
    } catch (error) {
      message.error('閲嶇疆瀵嗙爜澶辫触: ' + (error.response?.data?.detail || error.message));
    }
  };

  const deactivateUser = (record) => {
    Modal.confirm({
      title: '鍋滅敤鐢ㄦ埛',
      content: `纭鍋滅敤 ${record.full_name || record.username} 鍚楋紵鍋滅敤鍚庤璐﹀彿涓嶈兘鍐嶇櫥褰曘€俙,
      okText: '鍋滅敤',
      okButtonProps: { danger: true },
      cancelText: '鍙栨秷',
      onOk: async () => {
        try {
          await usersApi.deactivate(record.id);
          message.success('鐢ㄦ埛宸插仠鐢?);
          await loadUsers();
        } catch (error) {
          message.error('鍋滅敤澶辫触: ' + (error.response?.data?.detail || error.message));
        }
      },
    });
  };

  const listToText = (items = []) => (Array.isArray(items) ? items.join('\n') : '');

  const textToList = (value = '') => String(value || '')
    .split(/\r?\n|,|锛?)
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
      message.success('骞冲彴瑙勫垯宸蹭繚瀛?);
      setPolicyModalOpen(false);
      setEditingPolicy(null);
      await loadPlatformPolicies();
    } catch (error) {
      message.error('淇濆瓨骞冲彴瑙勫垯澶辫触: ' + (error.response?.data?.detail || error.message));
    }
  };

  const openArchetypeEdit = (record) => {
    setEditingArchetype(record);
    archetypeForm.resetFields();
    archetypeForm.setFieldsValue({
      raw_json: JSON.stringify(record.raw || {}, null, 2),
    });
    setArchetypeModalOpen(true);
  };

  const submitQuestionArchetype = async (values) => {
    if (!editingArchetype?.industry) return;
    let payload;
    try {
      payload = JSON.parse(values.raw_json || '{}');
    } catch (error) {
      message.error('琛屼笟妯℃澘涓嶆槸鍚堟硶 JSON锛岃妫€鏌ユ嫭鍙枫€侀€楀彿鍜屽紩鍙?);
      return;
    }
    try {
      await questionArchetypesApi.update(editingArchetype.industry, payload);
      message.success('琛屼笟闂妯℃澘宸蹭繚瀛?);
      setArchetypeModalOpen(false);
      setEditingArchetype(null);
      await loadQuestionArchetypes();
      await loadQuestionLearningSuggestions();
    } catch (error) {
      message.error('淇濆瓨琛屼笟闂妯℃澘澶辫触: ' + (error.response?.data?.detail || error.message));
    }
  };

  const applyTemplateSuggestion = async (record) => {
    try {
      await questionArchetypesApi.applySuggestion(record);
      message.success('妯℃澘浼樺寲寤鸿宸插啓鍏ヨ涓氭ā鏉垮簱');
      await Promise.all([loadQuestionArchetypes(), loadQuestionLearningSuggestions()]);
    } catch (error) {
      message.error('搴旂敤妯℃澘浼樺寲寤鸿澶辫触: ' + (error.response?.data?.detail || error.message));
    }
  };

  const columns = [
    {
      title: '鐢ㄦ埛',
      key: 'user',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.full_name || record.username}</Text>
          <Text type="secondary">{record.username}</Text>
        </Space>
      ),
    },
    { title: '閭', dataIndex: 'email', key: 'email' },
    {
      title: '瑙掕壊',
      dataIndex: 'role',
      key: 'role',
      render: (role) => <Tag color={role === 'admin' ? 'red' : 'blue'}>{roleLabels[role] || role}</Tag>,
    },
    {
      title: '鐘舵€?,
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active) => active ? <Tag color="green">鍚敤</Tag> : <Tag>鍋滅敤</Tag>,
    },
    {
      title: '鍒涘缓鏃堕棿',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '鎿嶄綔',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button type="link" onClick={() => openEdit(record)}>缂栬緫</Button>
          <Button type="link" onClick={() => openPassword(record)}>閲嶇疆瀵嗙爜</Button>
          <Button
            type="link"
            danger
            disabled={!record.is_active || record.id === currentUser?.id}
            onClick={() => deactivateUser(record)}
          >
            鍋滅敤
          </Button>
        </Space>
      ),
    },
  ];

  const platformPolicyColumns = [
    {
      title: '骞冲彴',
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
      title: '瀛楁暟寤鸿',
      dataIndex: 'length',
      key: 'length',
      width: 150,
    },
    {
      title: '缁撴瀯',
      dataIndex: 'format',
      key: 'format',
      width: 220,
      ellipsis: true,
    },
    {
      title: '寮曟祦绛栫暐',
      dataIndex: 'contact_policy',
      key: 'contact_policy',
      width: 150,
      render: (value) => {
        const labels = {
          owned_channel_allowed: '鑷湁娓犻亾鍙壙鎺?,
          soft_reference_only: '鍙仛寮辨彁绀?,
          avoid_direct_contact: '閬垮厤鐩存帴寮曟祦',
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
      title: 'AIGC鏍囪瘑',
      dataIndex: 'ai_label_required',
      key: 'ai_label_required',
      width: 110,
      render: (value) => value ? <Tag color="purple">寤鸿鏍囪瘑</Tag> : <Tag>涓嶅己鍒?/Tag>,
    },
    {
      title: '閫傚悎鍐呭',
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
      title: '楂橀闄╄瘝',
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
      title: '鎿嶄綔',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => openPolicyEdit(record)}>缂栬緫</Button>
      ),
    },
  ];

  const questionArchetypeColumns = [
    {
      title: '琛屼笟',
      dataIndex: 'industry',
      key: 'industry',
      width: 180,
      fixed: 'left',
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          {record.extends && <Text type="secondary">缁ф壙锛歿record.extends}</Text>}
        </Space>
      ),
    },
    {
      title: '涓讳綋绉板懠',
      dataIndex: 'entity_label',
      key: 'entity_label',
      width: 110,
      render: (value) => <Tag color="blue">{value || '鏈嶅姟鍟?}</Tag>,
    },
    {
      title: '鍏滃簳鏈嶅姟璇?,
      key: 'fallback',
      width: 180,
      render: (_, record) => record.fallback_service || `鍝佺墝鍚?+ ${record.fallback_service_suffix || '鏈嶅姟'}`,
    },
    {
      title: '楠岃瘉闂硶',
      key: 'trust',
      width: 280,
      ellipsis: true,
      render: (_, record) => record.copy?.verified_question || record.copy?.trust_question || '-',
    },
    {
      title: '杞寲闂硶',
      key: 'conversion',
      width: 260,
      ellipsis: true,
      render: (_, record) => record.copy?.process_question || '-',
    },
    {
      title: '绂佺敤璇?,
      dataIndex: 'forbidden_terms',
      key: 'forbidden_terms',
      width: 260,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.slice(0, 6).map((item) => <Tag key={item} color="orange">{item}</Tag>)}
        </Space>
      ),
    },
    {
      title: '鎿嶄綔',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => openArchetypeEdit(record)}>缂栬緫</Button>
      ),
    },
  ];

  const templateSuggestionColumns = [
    {
      title: '琛屼笟',
      dataIndex: 'industry',
      key: 'industry',
      width: 160,
      fixed: 'left',
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">{record.events || 0} 鏉′汉宸ヨ皟鏁?/Text>
        </Space>
      ),
    },
    {
      title: '寤鸿鏂板绂佺敤璇?,
      dataIndex: 'add_forbidden_terms',
      key: 'add_forbidden_terms',
      width: 240,
      render: (items = []) => (
        <Space wrap size={4}>
          {items.length ? items.map((item) => <Tag color="orange" key={item}>{item}</Tag>) : <Text type="secondary">鏆傛棤</Text>}
        </Space>
      ),
    },
    {
      title: '姝ｅ悜鏍蜂緥',
      dataIndex: 'positive_examples',
      key: 'positive_examples',
      width: 360,
      render: (items = []) => (
        <Space direction="vertical" size={2}>
          {items.slice(0, 3).map((item) => <Text key={item} ellipsis>{item}</Text>)}
          {!items.length && <Text type="secondary">鏆傛棤</Text>}
        </Space>
      ),
    },
    {
      title: '鍙嶅悜鏍蜂緥',
      dataIndex: 'negative_examples',
      key: 'negative_examples',
      width: 360,
      render: (items = []) => (
        <Space direction="vertical" size={2}>
          {items.slice(0, 3).map((item) => <Text key={item} ellipsis>{item}</Text>)}
          {!items.length && <Text type="secondary">鏆傛棤</Text>}
        </Space>
      ),
    },
    {
      title: '寤鸿鍘熷洜',
      dataIndex: 'reason',
      key: 'reason',
      width: 320,
      ellipsis: true,
    },
    {
      title: '鎿嶄綔',
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Button
          type="link"
          onClick={() => Modal.confirm({
            title: '纭鍐欏叆琛屼笟妯℃澘搴擄紵',
            content: '鍐欏叆鍚庝細褰卞搷鍚庣画鏂扮敓鎴愮殑闂鐭╅樀锛涘凡缁忓瓨鍦ㄧ殑闂涓嶄細鑷姩鏀瑰彉銆?,
            okText: '纭鍐欏叆',
            cancelText: '鍙栨秷',
            onOk: () => applyTemplateSuggestion(record),
          })}
        >
          纭鍐欏叆
        </Button>
      ),
    },
  ];

  if (!isAdmin) {
    return (
      <div>
        <Title level={2}>绯荤粺璁剧疆</Title>
        <Alert
          type="warning"
          showIcon
          message="褰撳墠璐﹀彿娌℃湁鐢ㄦ埛绠＄悊鏉冮檺"
          description="鐢ㄦ埛涓庤鑹茬鐞嗕粎绠＄悊鍛樺彲鎿嶄綔銆備綘浠嶅彲浠ョ户缁娇鐢ㄨ嚜宸辫鑹插厑璁哥殑椤圭洰銆佸唴瀹广€佺洃娴嬬瓑鍔熻兘銆?
        />
      </div>
    );
  }

  return (
    <div>
      <Space align="start" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={2}>绯荤粺璁剧疆</Title>
          <Paragraph type="secondary">
            绠＄悊鏈湴搴旂敤璐﹀彿涓?RBAC 瑙掕壊銆傚叧閿搷浣滀細浠ュ悗绔櫥褰曠敤鎴蜂负鍑嗗啓鍏ョ‘璁や汉銆佸鎵逛汉鍜屽彂甯冧汉銆?          </Paragraph>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>鍒锋柊</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>鏂板缓鐢ㄦ埛</Button>
        </Space>
      </Space>

      <Card
        title={<Space><SafetyOutlined /> 鐢ㄦ埛涓庤鑹?/Space>}
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

      <Card title="瑙掕壊璇存槑" style={{ marginTop: 16 }}>
        <Space wrap>
          {roles.map((role) => (
            <Tag key={role.value} color={role.value === 'admin' ? 'red' : 'blue'}>
              {role.label}: {role.description}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card
        title="骞冲彴閫傞厤瑙勫垯"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadPlatformPolicies}>鍒锋柊瑙勫垯</Button>}
      >
        <Paragraph type="secondary">
          杩欓噷灞曠ず鏂囩珷鐢熸垚銆佸悎瑙勬鏌ュ拰鍙戝竷寤鸿鍏辩敤鐨勫钩鍙拌鍒欍€傜敓鎴愬钩鍙扮鏃讹紝绯荤粺浼氭寜杩欎簺瑙勫垯鎺у埗缁撴瀯銆佸瓧鏁般€佸紩娴佹柟寮忓拰楂橀闄╄〃杈俱€?        </Paragraph>
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

      <Card
        title="琛屼笟闂妯℃澘"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadQuestionArchetypes}>鍒锋柊妯℃澘</Button>}
      >
        <Paragraph type="secondary">
          杩欓噷鎺у埗闂搴撶敓鎴愭椂鐨勮涓氫富浣撶О鍛笺€佸彲淇￠獙璇侀棶娉曘€佽浆鍖栨壙鎺ラ棶娉曞拰琛屼笟绂佺敤璇嶃€傚悗缁亣鍒扮浉鍚岃涓氭椂锛岀郴缁熶細澶嶇敤杩欎簺妯℃澘鐢熸垚鏇寸ǔ瀹氱殑闂鐭╅樀銆?        </Paragraph>
        <Table
          rowKey="industry"
          columns={questionArchetypeColumns}
          dataSource={questionArchetypes}
          loading={archetypeLoading}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 1360 }}
          size="small"
        />
      </Card>

      <Card
        title="闂妯℃澘浼樺寲寤鸿"
        style={{ marginTop: 16 }}
        extra={<Button icon={<ReloadOutlined />} onClick={loadQuestionLearningSuggestions}>鍒锋柊寤鸿</Button>}
      >
        <Paragraph type="secondary">
          鐢ㄦ埛鏂板銆佹敼鍐欍€佸垹闄ゆ垨绂佺敤闂鍚庯紝绯荤粺浼氭妸杩欎簺浜哄伐璋冩暣姹囨€绘垚妯℃澘浼樺寲寤鸿銆傜鐞嗗憳纭鍚庯紝鎵嶄細鍐欏叆琛屼笟妯℃澘搴擄紝渚涘悗缁悓绫婚」鐩敓鎴愰棶棰樼煩闃垫椂澶嶇敤銆?        </Paragraph>
        <Table
          rowKey={(record) => `${record.industry}-${(record.feedback_ids || []).join('-')}`}
          columns={templateSuggestionColumns}
          dataSource={templateSuggestions}
          loading={suggestionLoading}
          pagination={{ pageSize: 6 }}
          scroll={{ x: 1560 }}
          size="small"
          locale={{ emptyText: '鏆傛棤寰呯‘璁ょ殑妯℃澘浼樺寲寤鸿' }}
        />
      </Card>

      <Modal
        title={editingUser ? '缂栬緫鐢ㄦ埛' : '鏂板缓鐢ㄦ埛'}
        open={userModalOpen}
        onCancel={() => setUserModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submitUser}>
          {!editingUser && (
            <Form.Item name="username" label="鐢ㄦ埛鍚? rules={[{ required: true, message: '璇疯緭鍏ョ敤鎴峰悕' }]}>
              <Input />
            </Form.Item>
          )}
          <Form.Item name="email" label="閭" rules={[{ required: true, type: 'email', message: '璇疯緭鍏ユ湁鏁堥偖绠? }]}>
            <Input />
          </Form.Item>
          <Form.Item name="full_name" label="濮撳悕">
            <Input />
          </Form.Item>
          <Form.Item name="role" label="瑙掕壊" rules={[{ required: true, message: '璇烽€夋嫨瑙掕壊' }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item name="is_active" label="鍚敤鐘舵€? valuePropName="checked">
            <Switch checkedChildren="鍚敤" unCheckedChildren="鍋滅敤" />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="鍒濆瀵嗙爜" rules={[{ required: true, message: '璇疯緭鍏ュ垵濮嬪瘑鐮? }, { min: 6, message: '鑷冲皯 6 浣? }]}>
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={`閲嶇疆瀵嗙爜锛?{passwordUser?.full_name || passwordUser?.username || ''}`}
        open={passwordModalOpen}
        onCancel={() => setPasswordModalOpen(false)}
        onOk={() => passwordForm.submit()}
        destroyOnClose
      >
        <Form form={passwordForm} layout="vertical" onFinish={submitPassword}>
          <Form.Item name="password" label="鏂板瘑鐮? rules={[{ required: true, message: '璇疯緭鍏ユ柊瀵嗙爜' }, { min: 6, message: '鑷冲皯 6 浣? }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`缂栬緫骞冲彴瑙勫垯锛?{editingPolicy?.name || editingPolicy?.platform || ''}`}
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
          <Form.Item name="name" label="骞冲彴鍚嶇О" rules={[{ required: true, message: '璇峰～鍐欏钩鍙板悕绉? }]}>
            <Input />
          </Form.Item>
          <Form.Item name="style" label="鎺ㄨ崘椋庢牸">
            <TextArea rows={2} placeholder="渚嬪锛氭悳绱㈠弸濂姐€佺粨鏋勬竻鏅般€佷簨瀹炲厖鍒嗐€佸急骞垮憡" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="length" label="瀛楁暟璇存槑" style={{ flex: 1 }}>
              <Input placeholder="渚嬪锛?00-3000瀛? />
            </Form.Item>
            <Form.Item name="min_words" label="鏈€灏戝瓧鏁?>
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item name="max_words" label="鏈€澶氬瓧鏁?>
              <InputNumber min={0} />
            </Form.Item>
          </Space>
          <Form.Item name="format" label="鎺ㄨ崘缁撴瀯">
            <TextArea rows={2} placeholder="渚嬪锛氶棶棰樼粨璁?鍒ゆ柇鏍囧噯+浜嬪疄璇佹嵁+寤鸿" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={16}>
            <Form.Item name="contact_policy" label="寮曟祦绛栫暐" style={{ flex: 1 }}>
              <Select>
                <Select.Option value="owned_channel_allowed">鑷湁娓犻亾鍙壙鎺?/Select.Option>
                <Select.Option value="soft_reference_only">鍙仛寮辨彁绀?/Select.Option>
                <Select.Option value="avoid_direct_contact">閬垮厤鐩存帴寮曟祦</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="ai_label_required" label="寤鸿 AIGC 鏍囪瘑" valuePropName="checked">
              <Switch checkedChildren="寤鸿" unCheckedChildren="涓嶅己鍒? />
            </Form.Item>
          </Space>
          <Form.Item name="title_rules_text" label="鏍囬瑙勫垯锛堜竴琛屼竴鏉★級">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="forbidden_patterns_text" label="楂橀闄?绂佹琛ㄨ揪锛堜竴琛屼竴涓瘝锛?>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="warning_patterns_text" label="璋ㄦ厧琛ㄨ揪锛堜竴琛屼竴涓瘝锛?>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="recommended_content_types_text" label="閫傚悎鍐呭绫诲瀷锛堜竴琛屼竴涓級">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`缂栬緫琛屼笟闂妯℃澘锛?{editingArchetype?.industry || ''}`}
        open={archetypeModalOpen}
        onCancel={() => {
          setArchetypeModalOpen(false);
          setEditingArchetype(null);
        }}
        onOk={() => archetypeForm.submit()}
        width={860}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="淇敼鍚庝細褰卞搷鍚庣画鏂扮敓鎴愮殑闂搴?
          description="宸茬粡鐢熸垚骞惰惤搴撶殑鏃ч棶棰樹笉浼氳嚜鍔ㄦ敼鍙橈紱闇€瑕侀噸鏂扮敓鎴愰棶棰樺簱鎴栨墜鍔ㄧ紪杈戞棫闂銆?
        />
        <Form form={archetypeForm} layout="vertical" onFinish={submitQuestionArchetype}>
          <Form.Item
            name="raw_json"
            label="妯℃澘 JSON"
            rules={[{ required: true, message: '璇峰～鍐欐ā鏉?JSON' }]}
          >
            <TextArea rows={18} style={{ fontFamily: 'Consolas, monospace' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default Settings;
