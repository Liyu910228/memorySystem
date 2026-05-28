import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowRight, Brain, CheckCircle2, Clipboard, Database, Edit3, Eye, EyeOff, FileText, FlaskConical, KeyRound, LayoutDashboard, LogOut, MessageSquare, Plus, RefreshCw, Save, Send, Settings, Sparkles, Trash2, XCircle } from 'lucide-react';
import './styles.css';
import loginReference from './assets/login-reference.jpeg';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const layers = [
  { value: 'profile', label: '个人基本信息' },
  { value: 'long_term', label: '长期记忆' },
  { value: 'temporary', label: '临时记忆' },
];
const EDIT_PAGE_SIZE = 10;
const sections = [
  {
    key: 'overview',
    label: '概览',
    title: '个人记忆服务',
    subtitle: '查看系统状态和常用入口',
    icon: LayoutDashboard,
  },
  {
    key: 'ingest',
    label: '记忆抽取',
    title: 'HTTP 记忆抽取',
    subtitle: '提交用户问题并抽取个人记忆',
    icon: MessageSquare,
  },
  {
    key: 'read',
    label: '读取记忆',
    title: '读取记忆',
    subtitle: '按 ldapId 查询用户可用记忆',
    icon: Database,
  },
  {
    key: 'edit',
    label: '用户记忆',
    title: '用户记忆编辑',
    subtitle: '逐条新增、保存或删除用户记忆',
    icon: Brain,
  },
  {
    key: 'markdown',
    label: 'Markdown',
    title: 'Markdown 镜像',
    subtitle: '查看和维护用户记忆文件镜像',
    icon: FileText,
  },
  {
    key: 'model',
    label: '模型设置',
    title: '模型设置',
    subtitle: '管理当前模型配置和供应商',
    icon: Settings,
  },
];
const personalSections = sections.filter(section => ['read', 'edit'].includes(section.key));
const apiDocs = [
  {
    title: '写入并抽取个人记忆',
    badge: 'POST',
    path: '/api/dialogue-memories',
    description: '业务系统把员工 ldapId 和用户原始问题传入，服务会自动抽取可长期保存的个人记忆。',
    request: `curl --location --request POST '[origin]/api/dialogue-memories' \\
--header 'Content-Type: application/json' \\
--data-raw '{
  "ldapId": "alice001",
  "displayName": "Alice",
  "question": "记住，我喜欢先看结论，再看详细分析。"
}'`,
    params: [
      ['ldapId', 'string', '必填，员工 LDAP ID，也是个人记忆隔离键。'],
      ['question', 'string', '必填，用户本次输入或需要抽取的原始文本。'],
      ['displayName', 'string', '可选，首次创建员工记录时用于展示名称。'],
      ['aiReply', 'string', '可选，兼容旧调用方；当前抽取以 question 为主。'],
    ],
    response: `{
  "ldapId": "alice001",
  "saved": 2
}`,
  },
  {
    title: '读取员工全部或分层记忆',
    badge: 'GET',
    path: '/api/dialogue-memories/{ldapId}',
    description: '业务系统按 ldapId 拉取员工已沉淀的个人记忆，可选 layer 只读取某一层。',
    request: `curl --location --request GET '[origin]/api/dialogue-memories/alice001?layer=long_term'`,
    params: [
      ['ldapId', 'path', '必填，员工 LDAP ID。'],
      ['layer', 'query', '可选：profile / long_term / temporary。'],
      ['q', 'query', '可选，按记忆内容关键字模糊检索。'],
    ],
    response: `{
  "ldapId": "alice001",
  "content": "长期记忆：该员工喜欢先看结论，再看详细分析；"
}`,
  },
  {
    title: '个人 token 访问与编辑',
    badge: 'TOKEN',
    path: '/?token=<jwt>',
    description: '个人访问链接会从 JWT audience 识别本人 ldapId；个人 API 调用时在请求头传 token。',
    request: `curl --location --request GET '[origin]/api/personal/memories?layer=profile' \\
--header 'token: [jwt-token]'`,
    params: [
      ['token', 'header/url', '必填，JWT 的 audience[0] 应为员工 ldapId。'],
      ['layer', 'query', '可选：profile / long_term / temporary。'],
      ['content', 'body', '个人新增或编辑记忆时传入。'],
    ],
    response: `[
  {
    "id": 9,
    "content": "本人偏好中文简洁摘要。",
    "layer": "profile",
    "status": "active"
  }
]`,
  },
];
const extractionPrompt = `从以下员工输入中抽取个人记忆。只返回 JSON 数组，
每项包含 content、layer、memory_type、confidence。不要返回解释文字。
如果一句话里同时包含姓名、部门、偏好、当前任务等多个事实，必须拆成多条记忆，不要合并或遗漏。
content 必须保留关键实体原文，例如姓名、部门、岗位、偏好对象。
layer 只能是 profile、long_term、temporary。
profile 用于姓名、岗位、部门、联系方式等个人基本信息；
long_term 用于长期偏好、工作习惯、稳定背景；
temporary 用于短期上下文、当前任务、阶段性状态。`;
const memoryLayerGuide = [
  {
    layer: 'profile',
    name: '个人基本信息',
    summary: '姓名、年龄、岗位、部门、联系方式等稳定身份信息。',
    example: '我是李玉，今年35岁',
  },
  {
    layer: 'long_term',
    name: '长期记忆',
    summary: '长期偏好、工作习惯、稳定背景，后续对话长期有用。',
    example: '我喜欢先看结论',
  },
  {
    layer: 'temporary',
    name: '短期记忆',
    summary: '当前任务、近期关注事项、阶段性上下文；系统只保留最近 5 天汇总。',
    example: '今天临时要准备月度复盘',
  },
];
const extractionExampleInput = '我是李玉，今年35岁，我喜欢先看结论，今天临时要准备月度复盘。';
const extractionExampleJson = `[
  {
    "content": "我是李玉，今年35岁",
    "layer": "profile",
    "memory_type": "profile",
    "confidence": 0.95
  },
  {
    "content": "我喜欢先看结论",
    "layer": "long_term",
    "memory_type": "preference",
    "confidence": 0.9
  },
  {
    "content": "今天临时要准备月度复盘",
    "layer": "temporary",
    "memory_type": "context",
    "confidence": 0.85
  }
]`;
const extractionExampleOutput = `{
  "ldapId": "liyu",
  "content": "个人基本信息：我是李玉，今年35岁；长期记忆：我喜欢先看结论；临时记忆：最近 5 天关注：今天临时要准备月度复盘；"
}`;

async function api(path, options = {}) {
  const token = localStorage.getItem('adminToken');
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function personalApi(path, personalToken, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  headers.token = personalToken;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function AdminLogin({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setError('');
    const form = new FormData();
    form.append('username', username);
    form.append('password', password);
    try {
      const result = await api('/auth/login', { method: 'POST', body: form });
      localStorage.setItem('adminToken', result.access_token);
      onLogin();
    } catch {
      setError('管理员登录失败');
    }
  }

  return (
    <form className="admin-login" onSubmit={submit}>
      <div className="login-kicker">ACCOUNT LOGIN</div>
      <h1>欢迎回来</h1>
      <p className="login-subtitle">登录后继续管理个人记忆抽取、模型配置与 Markdown 镜像。</p>
      <label>
        账号
        <input value={username} onChange={event => setUsername(event.target.value)} placeholder="请输入账号" />
      </label>
      <label>
        密码
        <span className="password-field">
          <input
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={event => setPassword(event.target.value)}
            placeholder="请输入密码"
          />
          <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? '隐藏密码' : '显示密码'}>
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        </span>
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary login-submit" type="submit">登录系统 <ArrowRight size={18} /></button>
    </form>
  );
}

function LoginPage({ onLogin }) {
  return (
    <main className="login-page">
      <section className="login-visual" style={{ backgroundImage: `url(${loginReference})` }}>
        <div className="login-visual-overlay" />
        <div className="login-brand">
          <div className="login-logo"><Sparkles size={28} /></div>
          <div>
            <span>SNOW MEMORY</span>
            <strong>员工个人记忆系统</strong>
          </div>
        </div>
        <div className="login-message">
          <h2>统一管理个人记忆、抽取、镜像与配置，让 AI 更懂每位员工。</h2>
        </div>
        <div className="login-feature-row">
          <div><strong>LDAP</strong><span>员工隔离</span></div>
          <div><strong>MEMORY</strong><span>三层记忆</span></div>
          <div><strong>MODEL</strong><span>模型配置</span></div>
        </div>
      </section>
      <section className="login-form-side">
        <div className="login-card">
          <AdminLogin onLogin={onLogin} />
          <div className="login-note">
            <span>测试账号</span>
            <code>test_admin / Memory@Test2026</code>
          </div>
        </div>
      </section>
    </main>
  );
}

function ModelConfig({ config, onSave }) {
  const blankForm = {
    name: '',
    base_url: '',
    api_key: '',
    chat_model: '',
    embedding_model: '',
    protocol: 'openai_compatible',
    is_enabled: true,
  };
  const [providers, setProviders] = useState([]);
  const [form, setForm] = useState(blankForm);
  const [editingId, setEditingId] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function fetchProviders() {
    try {
      setProviders(await api('/admin/model-providers'));
    } catch {
      setProviders([]);
    }
  }

  function startCreate() {
    setEditingId(null);
    setForm(blankForm);
    setNotice('');
    setError('');
  }

  function startEdit(provider) {
    setEditingId(provider.id);
    setForm({
      name: provider.name,
      base_url: provider.base_url,
      api_key: '',
      chat_model: provider.chat_model,
      embedding_model: provider.embedding_model,
      protocol: provider.protocol || 'openai_compatible',
      is_enabled: provider.is_enabled,
    });
    setNotice('');
    setError('');
  }

  async function submit(event) {
    event.preventDefault();
    setNotice('');
    setError('');
    const payload = {
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      chat_model: form.chat_model.trim(),
      embedding_model: form.embedding_model.trim(),
      protocol: form.protocol,
      is_enabled: form.is_enabled,
    };
    if (form.api_key.trim()) payload.api_key = form.api_key.trim();

    try {
      if (editingId) {
        await api(`/admin/model-providers/${editingId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
        setNotice('供应商已更新');
      } else {
        await api('/admin/model-providers', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setNotice('供应商已添加');
      }
      setEditingId(null);
      setForm(blankForm);
      await fetchProviders();
      onSave(await api('/admin/model-config'));
    } catch (err) {
      setError(err.message || '保存失败');
    }
  }

  async function activate(providerId) {
    setNotice('');
    setError('');
    try {
      const updated = await api(`/admin/model-providers/${providerId}/activate`, { method: 'POST' });
      onSave(updated);
      await fetchProviders();
      setNotice('当前供应商已切换');
    } catch (err) {
      setError(err.message || '切换失败');
    }
  }

  async function remove(providerId) {
    setNotice('');
    setError('');
    try {
      await api(`/admin/model-providers/${providerId}`, { method: 'DELETE' });
      if (editingId === providerId) startCreate();
      await fetchProviders();
      setNotice('供应商已删除');
    } catch (err) {
      setError(err.message || '删除失败');
    }
  }

  async function testProvider(providerId) {
    setNotice('');
    setError('');
    setTestingId(providerId);
    try {
      const result = await api(`/admin/model-providers/${providerId}/test`, { method: 'POST' });
      setTestResults(current => ({ ...current, [providerId]: result }));
      setNotice(result.ok ? `${result.provider_name} 测试通过` : `${result.provider_name} 测试未通过`);
    } catch (err) {
      setError(err.message || '测试失败');
    } finally {
      setTestingId(null);
    }
  }

  useEffect(() => {
    fetchProviders();
  }, [config]);

  const currentProvider = providers.find(provider => provider.is_default);

  return (
    <div className="model-console">
      <section className="current-model-card">
        <div>
          <span>当前模型设置</span>
          <h2>{config?.provider_name || currentProvider?.name || '默认供应商'}</h2>
          <p>{config?.base_url || currentProvider?.base_url || '暂无 Base URL'}</p>
        </div>
        <div className="model-summary-grid">
          <div><span>协议</span><strong>{config?.protocol || 'openai_compatible'}</strong></div>
          <div><span>记忆抽取模型</span><strong>{config?.chat_model || '-'}</strong></div>
          <div><span>向量模型</span><strong>{config?.embedding_model || '-'}</strong></div>
          <div><span>API Key</span><strong>{config?.api_key_configured ? `已配置 ${config?.api_key_hint || ''}` : '未配置'}</strong></div>
        </div>
      </section>

      <section className="provider-section">
        <div className="provider-header">
          <div>
            <h2>供应商列表</h2>
            <p>{providers.length} 个供应商配置；点击供应商可编辑详情</p>
          </div>
          <button type="button" onClick={startCreate}><Plus size={16} /> 添加供应商</button>
        </div>
        <div className="provider-list">
          {providers.map(provider => {
            const testResult = testResults[provider.id];
            return (
              <article key={provider.id} className={provider.is_default ? 'provider-row active' : 'provider-row'}>
                <button type="button" className="provider-main" onClick={() => startEdit(provider)}>
                  <span className="drag-handle">::</span>
                  <span className="provider-avatar">{provider.name.slice(0, 1)}</span>
                  <span className="provider-copy">
                    <strong>{provider.name}</strong>
                    <small>{provider.protocol} · {provider.chat_model} / {provider.embedding_model} · {provider.base_url}</small>
                    {testResult && (
                      <small className={testResult.ok ? 'provider-test ok' : 'provider-test fail'}>
                        {testResult.ok ? '测试通过' : testResult.message} · {testResult.latency_ms}ms
                      </small>
                    )}
                  </span>
                </button>
                <div className="provider-badges">
                  {provider.is_default && <span className="chip current"><CheckCircle2 size={14} /> 当前</span>}
                  <span className={provider.api_key_configured ? 'chip' : 'chip muted'}><KeyRound size={14} /> {provider.api_key_configured ? 'Key 已配置' : '未配置 Key'}</span>
                  {testResult && (
                    <span className={testResult.ok ? 'chip test-ok' : 'chip test-fail'}>
                      {testResult.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                      {testResult.ok ? '模型正常' : '模型异常'}
                    </span>
                  )}
                </div>
                <div className="provider-actions">
                  <button type="button" onClick={() => testProvider(provider.id)} disabled={testingId === provider.id || !provider.api_key_configured}>
                    <FlaskConical size={15} /> {testingId === provider.id ? '测试中' : '测试'}
                  </button>
                  <button type="button" onClick={() => activate(provider.id)} disabled={provider.is_default}>设为当前</button>
                  <button type="button" onClick={() => startEdit(provider)}><Edit3 size={15} /> 编辑</button>
                  <button type="button" className="danger" onClick={() => remove(provider.id)} disabled={provider.is_default}><Trash2 size={15} /> 删除</button>
                </div>
              </article>
            );
          })}
          {providers.length === 0 && <p className="empty">暂无供应商配置</p>}
        </div>
      </section>

      <form className="provider-form" onSubmit={submit}>
        <div className="provider-form-title">
          <h2>{editingId ? '编辑供应商' : '添加供应商'}</h2>
          {editingId && <button type="button" onClick={startCreate}>取消编辑</button>}
        </div>
        <div className="provider-form-grid">
          <label>供应商名称<input value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} required /></label>
          <label>协议类型
            <select value={form.protocol} onChange={event => setForm({ ...form, protocol: event.target.value })}>
              <option value="openai_compatible">OpenAI-compatible</option>
            </select>
          </label>
          <label className="span-2">Base URL<input value={form.base_url} onChange={event => setForm({ ...form, base_url: event.target.value })} required /></label>
          <label>记忆抽取模型<input value={form.chat_model} onChange={event => setForm({ ...form, chat_model: event.target.value })} required /></label>
          <label>向量模型<input value={form.embedding_model} onChange={event => setForm({ ...form, embedding_model: event.target.value })} required /></label>
          <label className="span-2">API Key<input value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })} placeholder={editingId ? '留空则不覆盖已有 Key' : '输入供应商 API Key'} /></label>
          <label className="provider-check"><input type="checkbox" checked={form.is_enabled} onChange={event => setForm({ ...form, is_enabled: event.target.checked })} />启用供应商</label>
        </div>
        {notice && <p className="notice">{notice}</p>}
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit"><Save size={16} /> {editingId ? '保存供应商' : '添加供应商'}</button>
      </form>
    </div>
  );
}

function MemoryCard({ memory, isAdmin, ldapId, onChanged, personalToken }) {
  const [content, setContent] = useState(memory.content);
  const [saveNotice, setSaveNotice] = useState('');

  useEffect(() => {
    setContent(memory.content);
  }, [memory]);

  async function save() {
    setSaveNotice('');
    const path = personalToken ? `/personal/memories/${memory.id}` : `/admin/memories/${ldapId}/${memory.id}`;
    const options = {
      method: 'PATCH',
      body: JSON.stringify({ content }),
    };
    if (personalToken) {
      await personalApi(path, personalToken, options);
    } else {
      await api(path, options);
    }
    setSaveNotice('已经保存');
    onChanged();
  }

  async function remove() {
    const path = personalToken ? `/personal/memories/${memory.id}` : `/admin/memories/${ldapId}/${memory.id}`;
    if (personalToken) {
      await personalApi(path, personalToken, { method: 'DELETE' });
    } else {
      await api(path, { method: 'DELETE' });
    }
    onChanged();
  }

  return (
    <article className="memory-card">
      <textarea
        value={content}
        onChange={event => {
          setContent(event.target.value);
          setSaveNotice('');
        }}
        disabled={!isAdmin && !personalToken}
      />
      <div className="memory-meta">
        {(isAdmin || personalToken) && <button className="icon-action" onClick={save}><Save size={15} /> 保存</button>}
        {(isAdmin || personalToken) && <button className="icon-action danger" onClick={remove}><Trash2 size={15} /> 删除</button>}
      </div>
      {saveNotice && <p className="memory-save-notice">{saveNotice}</p>}
    </article>
  );
}

function MemoryCreateForm({ ldapId, layer, onCreated, personalToken }) {
  const [content, setContent] = useState('');
  const [saveNotice, setSaveNotice] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (!ldapId.trim() || !content.trim()) return;
    setSaveNotice('');
    const path = personalToken ? '/personal/memories' : `/admin/memories/${encodeURIComponent(ldapId)}`;
    const options = {
      method: 'POST',
      body: JSON.stringify({
        content,
        layer: layer || 'long_term',
        memory_type: 'manual',
        status: 'active',
      }),
    };
    if (personalToken) {
      await personalApi(path, personalToken, options);
    } else {
      await api(path, options);
    }
    setContent('');
    setSaveNotice('已经保存');
    onCreated();
  }

  return (
    <form className="memory-create-form" onSubmit={submit}>
      <label>新增记忆<textarea value={content} onChange={event => setContent(event.target.value)} placeholder="输入要新增的用户记忆" /></label>
      <div className="memory-create-row">
        <button className="primary" type="submit"><Save size={15} /> 新增</button>
      </div>
      {saveNotice && <p className="memory-save-notice">{saveNotice}</p>}
    </form>
  );
}

function MarkdownViewer({ markdown, canEdit, onSave }) {
  const [activeLayer, setActiveLayer] = useState('profile');
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState('');
  const active = markdown?.[activeLayer];

  useEffect(() => {
    setDraft(active?.content || '');
    setSaveNotice('');
  }, [activeLayer, active?.content]);

  if (!markdown) {
    return <p className="empty">输入 ldapId 后，可查询对应 Markdown 文件。</p>;
  }

  async function saveMarkdown() {
    if (!canEdit || !active) return;
    setSaving(true);
    setSaveNotice('');
    try {
      await onSave(activeLayer, draft);
      setSaveNotice('文件已保存');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="markdown-viewer">
      <div className="markdown-actions">
        <div className="tabs">
          {layers.map(layer => (
            <button
              key={layer.value}
              className={activeLayer === layer.value ? 'tab active' : 'tab'}
              onClick={() => setActiveLayer(layer.value)}
            >
              {layer.label}
            </button>
          ))}
        </div>
        {canEdit && (
          <button className="primary md-save" onClick={saveMarkdown} disabled={saving}>
            <Save size={15} /> {saving ? '保存中' : '保存文件'}
          </button>
        )}
      </div>
      <div className="md-path">{active?.path || '暂无文件路径'}</div>
      {canEdit ? (
        <textarea className="md-editor" value={draft} onChange={event => setDraft(event.target.value)} />
      ) : (
        <pre>{active?.content || '暂无 Markdown 内容'}</pre>
      )}
      {saveNotice && <p className="notice">{saveNotice}</p>}
    </div>
  );
}

function ApiDocCard({ doc, origin }) {
  const [activeTab, setActiveTab] = useState('request');
  const [copied, setCopied] = useState(false);
  const requestText = doc.request.replaceAll('[origin]', origin);

  async function copyRequest() {
    try {
      await navigator.clipboard.writeText(requestText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="api-doc-card">
      <div className="api-doc-head">
        <div>
          <span className={`api-method api-method-${doc.badge.toLowerCase()}`}>{doc.badge}</span>
          <h3>{doc.title}</h3>
          <p>{doc.description}</p>
        </div>
        <code>{doc.path}</code>
      </div>
      <div className="api-tabs">
        <button type="button" className={activeTab === 'request' ? 'active' : ''} onClick={() => setActiveTab('request')}>请求示例</button>
        <button type="button" className={activeTab === 'params' ? 'active' : ''} onClick={() => setActiveTab('params')}>参数说明</button>
        <button type="button" className={activeTab === 'response' ? 'active' : ''} onClick={() => setActiveTab('response')}>响应示例</button>
      </div>
      {activeTab === 'request' && (
        <div className="api-code-wrap">
          <button type="button" onClick={copyRequest} aria-label="复制请求示例"><Clipboard size={16} />{copied ? '已复制' : '复制'}</button>
          <pre><code>{requestText}</code></pre>
        </div>
      )}
      {activeTab === 'params' && (
        <div className="api-param-table">
          {doc.params.map(([name, type, desc]) => (
            <div key={name}>
              <code>{name}</code>
              <span>{type}</span>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      )}
      {activeTab === 'response' && (
        <div className="api-code-wrap response-code">
          <pre><code>{doc.response}</code></pre>
        </div>
      )}
    </article>
  );
}

function MemoryExtractionGuide() {
  return (
    <section className="extraction-guide">
      <div className="extraction-guide-head">
        <div>
          <span>大模型抽取逻辑</span>
          <h2>记忆是怎么从一句话里抽出来的</h2>
          <p>业务系统只要传入员工 ldapId 和用户原始输入，系统会让大模型按规则拆出个人信息、长期记忆和短期记忆，最后读取时返回一段可直接给业务使用的简洁汇总。</p>
        </div>
      </div>

      <div className="extraction-flow">
        <div><strong>1</strong><span>业务传入</span><p><code>ldapId + question</code></p></div>
        <div><strong>2</strong><span>模型识别</span><p>按提示词抽取结构化 JSON</p></div>
        <div><strong>3</strong><span>分层保存</span><p>写入个人信息、长期、短期三层记忆</p></div>
        <div><strong>4</strong><span>汇总读取</span><p>返回简短清晰的 content 文本</p></div>
      </div>

      <div className="memory-layer-guide">
        {memoryLayerGuide.map(item => (
          <article key={item.layer}>
            <code>{item.layer}</code>
            <h3>{item.name}</h3>
            <p>{item.summary}</p>
            <span>{item.example}</span>
          </article>
        ))}
      </div>

      <div className="extraction-detail-grid">
        <article className="prompt-panel">
          <div className="section-eyebrow">当前真实提示词</div>
          <pre><code>{extractionPrompt}</code></pre>
        </article>
        <article className="example-panel">
          <div className="section-eyebrow">业务例子</div>
          <div className="example-step">
            <strong>用户输入</strong>
            <p>{extractionExampleInput}</p>
          </div>
          <div className="example-step">
            <strong>模型抽取</strong>
            <pre><code>{extractionExampleJson}</code></pre>
          </div>
          <div className="example-step">
            <strong>读取返回</strong>
            <pre><code>{extractionExampleOutput}</code></pre>
          </div>
        </article>
      </div>

      <div className="business-rules">
        <strong>给业务同学的判断口诀</strong>
        <p>描述“这个人是谁、喜欢什么、正在做什么”的内容可以保存；像“我是谁”“我叫什么”这种只是提问，不会保存为记忆。</p>
      </div>
    </section>
  );
}

function OverviewDocs({ onOpenIngest, onOpenRead }) {
  const origin = window.location.origin || 'http://119.45.222.120:10012';

  return (
    <section className="api-overview">
      <div className="api-overview-title">
        <div>
          <span>HTTP 调用说明</span>
          <h2>业务系统接入个人记忆服务</h2>
          <p>最小接入只需要两个接口：写入时传 `ldapId + question`，读取时按 `ldapId` 拉取可用记忆。</p>
        </div>
        <div className="api-overview-actions">
          <button type="button" onClick={onOpenIngest}><MessageSquare size={16} />在线试写</button>
          <button type="button" onClick={onOpenRead}><Database size={16} />在线读取</button>
        </div>
      </div>
      <div className="api-doc-list">
        <MemoryExtractionGuide />
        {apiDocs.map(doc => <ApiDocCard key={doc.title} doc={doc} origin={origin} />)}
      </div>
    </section>
  );
}

function App() {
  const initialPersonalToken = new URLSearchParams(window.location.search).get('token') || '';
  const [admin, setAdmin] = useState(null);
  const [personalToken] = useState(initialPersonalToken);
  const [personalError, setPersonalError] = useState('');
  const [activeSection, setActiveSection] = useState(initialPersonalToken ? 'read' : 'overview');
  const [modelConfig, setModelConfig] = useState(null);
  const [ldapId, setLdapId] = useState('alice001');
  const [question, setQuestion] = useState('记住，我喜欢中文简洁摘要。');
  const [readLdapId, setReadLdapId] = useState('alice001');
  const [readMemories, setReadMemories] = useState([]);
  const [readMarkdown, setReadMarkdown] = useState('');
  const [editLdapId, setEditLdapId] = useState('alice001');
  const [editMemories, setEditMemories] = useState([]);
  const [markdown, setMarkdown] = useState(null);
  const [markdownLdapId, setMarkdownLdapId] = useState('alice001');
  const [readLayerFilter, setReadLayerFilter] = useState('');
  const [editLayerFilter, setEditLayerFilter] = useState('profile');
  const [editPage, setEditPage] = useState(1);
  const [notice, setNotice] = useState('');
  const [markdownError, setMarkdownError] = useState('');
  const [readNotice, setReadNotice] = useState('');
  const [editNotice, setEditNotice] = useState('');
  const isPersonalMode = Boolean(personalToken);

  async function checkAdmin() {
    try {
      const me = await api('/auth/me');
      setAdmin(me);
      setModelConfig(await api('/admin/model-config'));
    } catch {
      setAdmin(null);
      setModelConfig(null);
      setMarkdown(null);
      localStorage.removeItem('adminToken');
    }
  }

  async function checkPersonal() {
    try {
      const me = await personalApi('/personal/me', personalToken);
      setReadLdapId(me.ldapId);
      setEditLdapId(me.ldapId);
      const [readResult, editResult] = await Promise.all([
        personalApi(`/personal/memories${readLayerFilter ? `?layer=${readLayerFilter}` : ''}`, personalToken),
        personalApi(`/personal/memories?layer=${editLayerFilter}`, personalToken),
      ]);
      setReadMemories(readResult);
      setReadMarkdown('');
      setEditMemories(editResult);
      setReadNotice(`已读取 ${readResult.length} 条记忆`);
      setEditNotice(`已读取 ${editResult.length} 条可编辑记忆`);
      setPersonalError('');
    } catch {
      setPersonalError('个人访问 token 无效，请从正确链接进入。');
    }
  }

  async function fetchMemories() {
    const suffix = readLayerFilter ? `?layer=${readLayerFilter}` : '';
    const result = isPersonalMode
      ? await personalApi(`/personal/memories${suffix}`, personalToken)
      : await api(`/dialogue-memories/${encodeURIComponent(readLdapId)}${suffix}`, { headers: {} });
    if (Array.isArray(result)) {
      setReadMemories(result);
      setReadMarkdown('');
      setReadNotice(`已读取 ${result.length} 条记忆`);
    } else {
      setReadMemories([]);
      setReadMarkdown(result.content || '');
      setReadNotice(result.content ? '已读取 Markdown 记忆汇总' : '暂无记忆');
    }
  }

  async function fetchEditMemories() {
    const result = isPersonalMode
      ? await personalApi(`/personal/memories?layer=${editLayerFilter}`, personalToken)
      : await api(`/admin/memories/${encodeURIComponent(editLdapId)}?layer=${editLayerFilter}`);
    setEditMemories(result);
    setEditNotice(`已读取 ${result.length} 条可编辑记忆`);
  }

  async function fetchMarkdown() {
    if (!admin) return;
    setMarkdownError('');
    try {
      setMarkdown(await api(`/admin/memories/${encodeURIComponent(markdownLdapId)}/markdown`));
    } catch {
      setMarkdown(null);
      setMarkdownError('未找到该 ldapId 的 Markdown 镜像，请先写入一条记忆。');
    }
  }

  async function saveMarkdown(layer, content) {
    const updated = await api(`/admin/memories/${encodeURIComponent(markdownLdapId)}/markdown/${layer}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
    setMarkdown(current => ({
      ...current,
      [layer]: updated,
    }));
  }

  async function refreshAll() {
    if (isPersonalMode) {
      await fetchMemories();
      await fetchEditMemories();
      return;
    }
    await fetchMemories();
    await fetchEditMemories();
    await fetchMarkdown();
  }

  async function submitDialogue(event) {
    event.preventDefault();
    const result = await api('/dialogue-memories', {
      method: 'POST',
      body: JSON.stringify({ ldapId, question }),
    });
    setNotice(`已保存 ${result.saved} 条记忆`);
    await refreshAll();
  }

  useEffect(() => {
    if (personalToken) {
      checkPersonal();
    } else if (localStorage.getItem('adminToken')) {
      checkAdmin();
    }
  }, []);

  const combinedReadMemories = readMemories
    .map(memory => memory.content.trim())
    .filter(Boolean)
    .join('；');
  const readDisplayContent = readMarkdown || combinedReadMemories;

  const activeEditLayer = layers.find(layer => layer.value === editLayerFilter) || layers[0];
  const activeEditMemories = editMemories.filter(memory => memory.layer === activeEditLayer.value);
  const editTotalPages = Math.max(1, Math.ceil(activeEditMemories.length / EDIT_PAGE_SIZE));
  const editCurrentPage = Math.min(editPage, editTotalPages);
  const pagedEditMemories = activeEditMemories.slice(
    (editCurrentPage - 1) * EDIT_PAGE_SIZE,
    editCurrentPage * EDIT_PAGE_SIZE,
  );

  useEffect(() => {
    setEditPage(1);
  }, [editLayerFilter, editLdapId]);

  if (!admin && !isPersonalMode) {
    return <LoginPage onLogin={checkAdmin} />;
  }

  const availableSections = isPersonalMode ? personalSections : sections;
  const activeSectionMeta = availableSections.find(section => section.key === activeSection) || availableSections[0];

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">M</div>
          <div>
            <strong>Memory AI</strong>
            <span>管理控制台</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {availableSections.map(section => {
            const Icon = section.icon;
            return (
              <button
                key={section.key}
                type="button"
                className={activeSection === section.key ? 'active' : ''}
                onClick={() => setActiveSection(section.key)}
              >
                <Icon size={17} />{section.label}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-user">
          <span>{isPersonalMode ? '个人用户' : '管理员'}</span>
          <strong>{isPersonalMode ? readLdapId : admin.display_name}</strong>
        </div>
      </aside>

      <div className="console-main">
        <header className="hero">
          <div>
            <h1>{activeSectionMeta.title}</h1>
            <p>{activeSectionMeta.subtitle}</p>
          </div>
          <div className="admin-state">
            <button type="button" onClick={refreshAll}><RefreshCw size={16} /></button>
            {!isPersonalMode && (
              <button type="button" onClick={() => { localStorage.removeItem('adminToken'); setAdmin(null); setModelConfig(null); setMarkdown(null); }}><LogOut size={16} />退出</button>
            )}
          </div>
        </header>

        {personalError && <div className="panel"><p className="error">{personalError}</p></div>}

        {!isPersonalMode && activeSection === 'overview' && (
          <section className="status-card">
            <div>
              <span>Memory AI 状态</span>
              <h2>当前为管理员工作台</h2>
              <p>通过左侧菜单进入对应功能，当前页面只显示选中的工作模块。</p>
            </div>
            <div className="status-actions">
              <button type="button" className="dark-action" onClick={refreshAll}><RefreshCw size={15} />刷新</button>
              <button type="button" onClick={() => setActiveSection('model')}><Settings size={15} />模型设置</button>
            </div>
          </section>
        )}

      <section className="content-shell">
        {!isPersonalMode && activeSection === 'overview' && (
          <OverviewDocs
            onOpenIngest={() => setActiveSection('ingest')}
            onOpenRead={() => setActiveSection('read')}
          />
        )}

        {!isPersonalMode && activeSection === 'ingest' && (
        <div className="panel">
          <h1>HTTP 记忆抽取</h1>
          <form className="dialogue-form" onSubmit={submitDialogue}>
            <label>ldapId<input value={ldapId} onChange={event => setLdapId(event.target.value)} /></label>
            <label>用户问题<textarea value={question} onChange={event => setQuestion(event.target.value)} /></label>
            {notice && <p className="notice">{notice}</p>}
            <button className="primary" type="submit"><Send size={16} /> POST 抽取记忆</button>
          </form>
        </div>
        )}

        {!isPersonalMode && activeSection === 'model' && (
        <div className="panel admin-panel">
          <ModelConfig config={modelConfig} onSave={setModelConfig} />
        </div>
        )}

        {activeSection === 'read' && (
        <div className="panel memory-panel">
          <div className="memory-toolbar">
            <h2>GET 读取记忆</h2>
            <label className="inline-search">ldapId<input value={readLdapId} onChange={event => setReadLdapId(event.target.value)} readOnly={isPersonalMode} /></label>
            <select value={readLayerFilter} onChange={event => setReadLayerFilter(event.target.value)}>
              <option value="">全部层级</option>
              {layers.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button onClick={fetchMemories} disabled={!readLdapId.trim()}><RefreshCw size={15} /> 读取</button>
          </div>
          {readNotice && <p className="notice toolbar-notice">{readNotice}</p>}
          <div className="combined-memory-card">
            {readDisplayContent || <span>暂无记忆</span>}
          </div>
        </div>
        )}

        {activeSection === 'edit' && (
        <div className="panel edit-memory-panel">
          <div className="memory-toolbar edit-toolbar">
            <h2>用户记忆编辑</h2>
            <label className="inline-search">ldapId<input value={editLdapId} onChange={event => setEditLdapId(event.target.value)} readOnly={isPersonalMode} /></label>
            <select value={editLayerFilter} onChange={event => setEditLayerFilter(event.target.value)}>
              {layers.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <button onClick={fetchEditMemories} disabled={!editLdapId.trim()}><RefreshCw size={15} /> 查询</button>
          </div>
          {editNotice && <p className="notice toolbar-notice">{editNotice}</p>}
          <MemoryCreateForm ldapId={editLdapId} layer={editLayerFilter} onCreated={fetchEditMemories} personalToken={personalToken} />
          <div className="layer-grid edit-layer-grid single-layer-grid">
            <section className="layer-column" key={activeEditLayer.value}>
              <h3>{activeEditLayer.label}</h3>
              {pagedEditMemories.map(memory => (
                <MemoryCard key={memory.id} memory={memory} ldapId={editLdapId} isAdmin={!!admin} personalToken={personalToken} onChanged={fetchEditMemories} />
              ))}
              {activeEditMemories.length === 0 && <p className="empty">暂无可编辑记忆</p>}
              {activeEditMemories.length > EDIT_PAGE_SIZE && (
                <div className="pagination">
                  <button
                    type="button"
                    onClick={() => setEditPage(page => Math.max(1, page - 1))}
                    disabled={editCurrentPage === 1}
                  >
                    上一页
                  </button>
                  <span>{editCurrentPage} / {editTotalPages}</span>
                  <button
                    type="button"
                    onClick={() => setEditPage(page => Math.min(editTotalPages, page + 1))}
                    disabled={editCurrentPage === editTotalPages}
                  >
                    下一页
                  </button>
                </div>
              )}
            </section>
          </div>
        </div>
        )}

        {!isPersonalMode && activeSection === 'markdown' && (
        <div className="panel markdown-panel">
          <div className="memory-toolbar">
            <label className="md-search">
              <span className="md-title"><FileText size={17} /> Markdown 镜像</span>
              ldapId
              <input value={markdownLdapId} onChange={event => setMarkdownLdapId(event.target.value)} placeholder="输入 ldapId 查询文件" />
            </label>
            <button onClick={fetchMarkdown} disabled={!admin || !markdownLdapId.trim()}><RefreshCw size={15} /> 查询文件</button>
          </div>
          {markdownError && <p className="error">{markdownError}</p>}
          <MarkdownViewer markdown={markdown} canEdit={!!admin} onSave={saveMarkdown} />
        </div>
        )}
      </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
