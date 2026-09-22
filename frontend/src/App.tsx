import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Copy,
  Database,
  History,
  LayoutDashboard,
  MessageSquare,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import { deleteApi, getApi, postApi } from "./api";

type Page = "overview" | "workspace" | "monitor" | "memories" | "conversations" | "tasks" | "settings";
type Message = { id: string; role: "user" | "assistant"; content: string };
type AgentStep = { agent: string; status: string; error?: string | null };
type OrchestrationResult = {
  task_id: string; status: string; agents_used: string[]; result: string; steps: AgentStep[];
};
type Memory = { memory_id: string; memory_text: string; memory_type: string; created_at?: string };
type Conversation = { conversation_id: string; title: string; updated_at?: string; created_at?: string };
type Task = {
  task_id: string;
  task_description: string;
  agents_used: string[];
  result_summary: string;
  status: string;
  created_at?: string;
  error_message?: string | null;
  started_at?: string;
  completed_at?: string;
  cancel_requested: boolean;
  approval_status?: string;
  approval_decision_at?: string;
  approval_reason?: string | null;
};
type BackgroundTask = Task;
type TaskListResponse = { items: Task[]; page: number; page_size: number; total: number };
type Summary = {
  total_tasks: number; completed_tasks: number; failed_tasks: number; running_tasks: number;
  recent_tasks: Task[]; recent_conversations: Conversation[]; available_agents: string[];
};

const navItems: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "workspace", label: "AI Workspace", icon: MessageSquare },
  { id: "monitor", label: "Agent Monitor", icon: Activity },
  { id: "memories", label: "Memories", icon: BrainCircuit },
  { id: "conversations", label: "Conversations", icon: History },
  { id: "tasks", label: "Task History", icon: Clock3 },
  { id: "settings", label: "Settings", icon: Settings },
];

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : "Unavailable";
}

function statusIcon(status: string) {
  return status === "completed" ? <CheckCircle2 size={16} /> : <XCircle size={16} />;
}

function MarkdownText({ content }: { content: string }) {
  const parts = content.split(/(```[\s\S]*?```)/g);
  return <div className="markdown">{parts.map((part, index) => part.startsWith("```") ? (
    <pre key={index}><code>{part.replace(/^```[a-zA-Z]*\n?/, "").replace(/```$/, "")}</code><button className="copy-button" onClick={() => void navigator.clipboard.writeText(part)} type="button"><Copy size={14} /> Copy</button></pre>
  ) : <p key={index}>{part}</p>)}</div>;
}

function App() {
  const [page, setPage] = useState<Page>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState<BackgroundTask | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setMode] = useState<"chat" | "orchestrate">("chat");
  const [orchestration, setOrchestration] = useState<OrchestrationResult | null>(null);
  const [draft, setDraft] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState("");
  const [memoryUsed, setMemoryUsed] = useState(false);
  const [taskFilter, setTaskFilter] = useState("all");
  const [taskSearch, setTaskSearch] = useState("");

  useEffect(() => {
    if (!activeTask || ["completed", "failed", "completed_with_errors", "cancelled"].includes(activeTask.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void getApi<BackgroundTask>(`/tasks/${activeTask.task_id}`)
        .then(setActiveTask)
        .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Unable to poll task status."));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeTask]);

  const loadData = useCallback(async () => {
    setLoadingData(true); setError("");
    try {
      const [nextSummary, nextMemories, nextConversations, nextTasks] = await Promise.all([
        getApi<Summary>("/dashboard/summary"), getApi<Memory[]>("/memory"),
        getApi<Conversation[]>("/conversations"),
        getApi<TaskListResponse>("/tasks?page=1&page_size=100"),
      ]);
      setSummary(nextSummary); setMemories(nextMemories); setConversations(nextConversations); setTasks(nextTasks.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load dashboard data.");
    } finally { setLoadingData(false); }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  async function sendMessage(event: FormEvent) {
    event.preventDefault(); const message = draft.trim();
    if (!message || isLoading) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: message }]);
    setDraft(""); setError(""); setOrchestration(null); setIsLoading(true);
    try {
      const result = await postApi<{ response?: string } & OrchestrationResult>(
        mode === "chat" ? "/chat" : "/orchestrate", { message },
      );
      setMemoryUsed(result.headers.get("X-Memory-Used") === "true");
      if (mode === "chat") setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: result.data.response || "" }]);
      else setOrchestration(result.data as OrchestrationResult);
      void loadData();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reach NexusFlow.");
    } finally { setIsLoading(false); }
  }

  async function saveMemory(event: FormEvent) {
    event.preventDefault(); if (!memoryDraft.trim()) return;
    try {
      const result = await postApi<Memory>("/memory", { memory_text: memoryDraft.trim(), memory_type: "user_saved" });
      setMemories((current) => [result.data, ...current]); setMemoryDraft("");
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to save memory."); }
  }

  async function submitBackgroundTask() {
    const description = draft.trim();
    if (!description || isLoading) return;
    setError(""); setDraft(""); setPage("tasks");
    try {
      const result = await postApi<{ task_id: string; status: string }>("/tasks/submit", { task_description: description });
      setActiveTask({
        task_id: result.data.task_id, status: result.data.status, task_description: description,
        agents_used: [], result_summary: "", cancel_requested: false,
      });
      void loadData();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to queue background task.");
    }
  }

  async function cancelTask(taskId: string) {
    try {
      const task = await postApi<BackgroundTask>(`/tasks/${taskId}/cancel`, {});
      setActiveTask(task.data);
      void loadData();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to cancel task."); }
  }

  async function retryTask(task: BackgroundTask) {
    try {
      const result = await postApi<{ task_id: string; status: string }>(`/tasks/${task.task_id}/retry`, {});
      setActiveTask({ ...task, task_id: result.data.task_id, status: result.data.status, result_summary: "", error_message: null, cancel_requested: false });
      void loadData();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to retry task."); }
  }

  async function decideTask(taskId: string, decision: "approve" | "reject") {
    try {
      const result = await postApi<BackgroundTask>(`/tasks/${taskId}/${decision}`, {});
      setActiveTask(result.data);
      void loadData();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update approval.");
    }
  }

  async function removeMemory(id: string) {
    if (!window.confirm("Delete this memory permanently?")) return;
    try { await deleteApi(`/memory/${id}`); setMemories((current) => current.filter((item) => item.memory_id !== id)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to delete memory."); }
  }

  async function openConversation(id: string) {
    try {
      const conversation = await getApi<{ messages: { message_id: string; role: "user" | "assistant"; content: string }[] }>(`/conversations/${id}`);
      setMessages(conversation.messages.map((message) => ({ id: message.message_id, role: message.role, content: message.content })));
      setPage("workspace");
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to open conversation."); }
  }

  const filteredTasks = useMemo(() => tasks.filter((task) =>
    (taskFilter === "all" || task.status === taskFilter) &&
    `${task.task_description} ${task.task_id}`.toLowerCase().includes(taskSearch.toLowerCase())
  ), [taskFilter, taskSearch, tasks]);

  function navigate(nextPage: Page) { setPage(nextPage); setSidebarOpen(false); }

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand"><div className="brand-mark"><BrainCircuit size={20} /></div><div><strong>NexusFlow</strong><span>AI ORCHESTRATION</span></div></div>
        <div className="sidebar-label">Workspace</div>
        <nav>{navItems.map(({ id, label, icon: Icon }) => <button className={page === id ? "nav-active" : ""} key={id} onClick={() => navigate(id)} type="button"><Icon size={17} />{label}</button>)}</nav>
        <div className="sidebar-footer"><div className="connection-dot" /> Local session connected</div>
      </aside>
      <section className="dashboard">
        <header className="topbar"><button className="mobile-toggle" onClick={() => setSidebarOpen((open) => !open)} type="button"><PanelLeft /></button><div><span className="breadcrumb">NEXUSFLOW /</span><strong>{navItems.find((item) => item.id === page)?.label}</strong></div><div className="topbar-actions"><button className="icon-button" onClick={() => void loadData()} title="Refresh dashboard" type="button"><RefreshCw size={17} /></button><span className="session-badge"><span className="status-dot" /> Session active</span></div></header>
        <div className="content">
          {error && <div className="global-error" role="alert">{error}<button onClick={() => setError("")} type="button"><XCircle size={16} /></button></div>}
          {page === "overview" && <Overview summary={summary} loading={loadingData} navigate={navigate} />}
          {page === "workspace" && <Workspace messages={messages} mode={mode} setMode={setMode} draft={draft} setDraft={setDraft} isLoading={isLoading} sendMessage={sendMessage} orchestration={orchestration} memoryUsed={memoryUsed} activeTask={activeTask} queueTask={submitBackgroundTask} clear={() => { setMessages([]); setOrchestration(null); }} />}
          {page === "monitor" && <Monitor orchestration={orchestration} summary={summary} activeTask={activeTask} cancel={cancelTask} retry={retryTask} decide={decideTask} />}
          {page === "memories" && <Memories memories={memories} draft={memoryDraft} setDraft={setMemoryDraft} save={saveMemory} remove={removeMemory} />}
          {page === "conversations" && <Conversations conversations={conversations} open={openConversation} />}
          {page === "tasks" && <Tasks tasks={filteredTasks} filter={taskFilter} setFilter={setTaskFilter} search={taskSearch} setSearch={setTaskSearch} activeTask={activeTask} cancel={cancelTask} retry={retryTask} decide={decideTask} />}
          {page === "settings" && <SettingsView />}
        </div>
      </section>
    </main>
  );
}

function PageHeader({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return <div className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{copy}</p></div></div>;
}

function Overview({ summary, loading, navigate }: { summary: Summary | null; loading: boolean; navigate: (page: Page) => void }) {
  const cards = [
    ["Total tasks", summary?.total_tasks ?? 0, <Activity />], ["Completed", summary?.completed_tasks ?? 0, <CheckCircle2 />],
    ["Failed", summary?.failed_tasks ?? 0, <XCircle />], ["Running", summary?.running_tasks ?? 0, <Clock3 />],
  ];
  return <><PageHeader eyebrow="Command center" title="Dashboard overview" copy="A live view of your orchestration workspace and persistent context." />
    <div className="stat-grid">{cards.map(([label, value, icon]) => <article className="stat-card" key={String(label)}><div className="stat-icon">{icon}</div><span>{label}</span><strong>{loading ? "—" : value}</strong></article>)}</div>
    <div className="overview-grid"><section className="panel"><div className="panel-title"><div><span className="eyebrow">Execution log</span><h2>Recent task activity</h2></div><button className="text-button" onClick={() => navigate("tasks")} type="button">View all <ChevronRight size={15} /></button></div>{summary?.recent_tasks.length ? summary.recent_tasks.map((task) => <TaskRow key={task.task_id} task={task} />) : <Empty title="No task activity" copy="Run a multi-agent task to see execution history here." />}</section><section className="panel"><div className="panel-title"><div><span className="eyebrow">Available workforce</span><h2>Agents</h2></div></div><div className="agent-list">{(summary?.available_agents || []).map((agent) => <div className="agent-card" key={agent}><span className="agent-avatar"><Users size={15} /></span><div><strong>{agent}</strong><small>{agent === "general" ? "Single-call assistant" : "Specialized agent"}</small></div><span className="agent-ready">Ready</span></div>)}</div></section></div>
  </>;
}

function TaskRow({ task, decide }: { task: Task; decide?: (id: string, decision: "approve" | "reject") => void }) {
  return <div className="task-row">
    <span className={`status-symbol ${task.status}`}>{statusIcon(task.status)}</span>
    <div><strong>{task.task_description}</strong><small>{task.agents_used.join(" · ") || "Awaiting agents"} · {formatDate(task.created_at)}</small></div>
    <div className="task-row-actions">
      <span className={`status-text ${task.status}`}>{task.approval_status === "pending" ? "approval required" : task.status}</span>
      {task.approval_status === "pending" && decide ? <><button className="small-button" onClick={() => decide(task.task_id, "approve")} type="button">Approve</button><button className="danger-button" onClick={() => decide(task.task_id, "reject")} type="button">Reject</button></> : null}
    </div>
  </div>;
}
function Empty({ title, copy }: { title: string; copy: string }) { return <div className="empty-block"><Database size={25} /><strong>{title}</strong><p>{copy}</p></div>; }

function Workspace(props: { messages: Message[]; mode: "chat" | "orchestrate"; setMode: (mode: "chat" | "orchestrate") => void; draft: string; setDraft: (value: string) => void; isLoading: boolean; sendMessage: (event: FormEvent) => void; orchestration: OrchestrationResult | null; memoryUsed: boolean; activeTask: BackgroundTask | null; queueTask: () => void; clear: () => void }) {
  return <><PageHeader eyebrow="AI workspace" title="Think with NexusFlow" copy="Chat directly, run the supervisor now, or queue a long-running task in the background." /><div className="workspace-toolbar"><div className="mode-switch"><button className={props.mode === "chat" ? "active" : ""} onClick={() => props.setMode("chat")} type="button">Quick chat</button><button className={props.mode === "orchestrate" ? "active" : ""} onClick={() => props.setMode("orchestrate")} type="button">Multi-agent task</button></div><button className="text-button" onClick={props.clear} type="button">Clear</button></div><section className="panel chat-panel"><div className="chat-scroll">{props.messages.length === 0 && !props.orchestration && !props.isLoading && !props.activeTask ? <Empty title={props.mode === "chat" ? "Start a conversation" : "Assign a task to the supervisor"} copy="Your responses and persisted history will appear here." /> : <>{props.messages.map((message) => <article className={`message-row ${message.role}`} key={message.id}><span className="message-label">{message.role === "user" ? "You" : "NexusFlow"}</span><div className="bubble">{message.role === "assistant" ? <MarkdownText content={message.content} /> : message.content}</div></article>)}{props.isLoading && <div className="loading-line"><span /><span /><span /> NexusFlow is thinking</div>}{props.orchestration && <OrchestrationCard result={props.orchestration} />}{props.activeTask && <BackgroundTaskCard task={props.activeTask} />}</>}</div>{props.memoryUsed && <div className="memory-banner"><BrainCircuit size={15} /> Relevant saved memory was used.</div>}<form className="composer" onSubmit={props.sendMessage}><input aria-label="Message NexusFlow" maxLength={4000} onChange={(event) => props.setDraft(event.target.value)} placeholder={props.mode === "chat" ? "Message NexusFlow..." : "Describe the task for your agent team..."} value={props.draft} /><button disabled={!props.draft.trim() || props.isLoading} type="submit"><Send size={17} /></button></form>{props.mode === "orchestrate" && <button className="queue-button" disabled={!props.draft.trim() || props.isLoading} onClick={props.queueTask} type="button"><Clock3 size={16} /> Queue as background task</button>}</section></>;
}

function OrchestrationCard({ result }: { result: OrchestrationResult }) { return <div className="orchestration-card"><div className="result-heading"><div><span className="eyebrow">Supervisor result</span><h2>{result.status}</h2></div><code>{result.task_id.slice(0, 8)}</code></div><MarkdownText content={result.result} /><div className="flow-line"><span>User task</span><ChevronRight /><span>Supervisor</span><ChevronRight />{result.steps.map((step) => <span className={`flow-agent ${step.status}`} key={step.agent}>{step.agent} {statusIcon(step.status)}</span>)}</div></div>; }

function BackgroundTaskCard({ task }: { task: BackgroundTask }) { return <div className="background-task"><span className={`status-symbol ${task.status}`}>{task.status === "completed" ? <CheckCircle2 size={15} /> : <Clock3 size={15} />}</span><div><strong>Background task {task.status}</strong><small>{task.task_description}</small>{task.error_message && <small className="task-error">{task.error_message}</small>}{task.result_summary && <MarkdownText content={task.result_summary} />}</div></div>; }
function Monitor({ orchestration, summary, activeTask, cancel, retry, decide }: { orchestration: OrchestrationResult | null; summary: Summary | null; activeTask: BackgroundTask | null; cancel: (id: string) => void; retry: (task: BackgroundTask) => void; decide: (id: string, decision: "approve" | "reject") => void }) { return <><PageHeader eyebrow="Observability" title="Agent monitor" copy="Execution data returned by the supervisor and background worker. No progress is fabricated." /><section className="panel monitor-panel"><div className="monitor-flow"><div className="flow-node"><MessageSquare /><strong>User task</strong><small>{activeTask?.task_description || "Completed request"}</small></div><ChevronRight /><div className="flow-node"><BrainCircuit /><strong>Supervisor</strong><small>{activeTask?.status || (orchestration ? "Completed response" : "No active task")}</small></div><ChevronRight /><div className="flow-node"><Users /><strong>Agents</strong><small>{activeTask?.agents_used.join(" · ") || orchestration?.agents_used.join(" · ") || "Awaiting a task"}</small></div><ChevronRight /><div className="flow-node"><CheckCircle2 /><strong>Result</strong><small>{activeTask?.status || orchestration?.status || "No result yet"}</small></div></div>{activeTask ? <div className="monitor-results"><BackgroundTaskCard task={activeTask} />{activeTask.approval_status === "pending" ? <div><button className="queue-button" onClick={() => decide(activeTask.task_id, "approve")} type="button">Approve task</button><button className="queue-button" onClick={() => decide(activeTask.task_id, "reject")} type="button">Reject task</button></div> : null}{activeTask.status === "running" || activeTask.status === "queued" ? <button className="queue-button" onClick={() => cancel(activeTask.task_id)} type="button">Cancel task</button> : null}{activeTask.status === "failed" || activeTask.status === "completed_with_errors" ? <button className="queue-button" onClick={() => retry(activeTask)} type="button">Retry task</button> : null}</div> : orchestration ? <div className="monitor-results">{orchestration.steps.map((step) => <div className="monitor-agent" key={step.agent}><span className={`agent-avatar ${step.status}`}>{statusIcon(step.status)}</span><div><strong>{step.agent}</strong><p>Execution reported as {step.status}. Start and completion timestamps are not provided by the current API.</p>{step.error && <small>{step.error}</small>}</div><span className={`status-text ${step.status}`}>{step.status}</span></div>)}</div> : <Empty title="No current orchestration result" copy={`Completed tasks in history: ${summary?.total_tasks ?? 0}. Run a task in AI Workspace to inspect its actual returned steps.`} />}</section></>; }

function Memories({ memories, draft, setDraft, save, remove }: { memories: Memory[]; draft: string; setDraft: (value: string) => void; save: (event: FormEvent) => void; remove: (id: string) => void }) { return <><PageHeader eyebrow="Persistent context" title="Memory management" copy="Store only useful, user-approved context. Memories remain scoped to this development session." /><section className="panel"><form className="memory-form" onSubmit={save}><input aria-label="New memory" maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="Save a preference or project fact..." value={draft} /><button disabled={!draft.trim()} type="submit"><Plus size={16} /> Save memory</button></form>{memories.length ? <div className="record-list">{memories.map((memory) => <div className="record" key={memory.memory_id}><div><span className="tag">{memory.memory_type}</span><p>{memory.memory_text}</p><small>Created {formatDate(memory.created_at)}</small></div><button className="danger-button" onClick={() => remove(memory.memory_id)} type="button"><Trash2 size={15} /></button></div>)}</div> : <Empty title="No saved memories" copy="Add a preference or ongoing project fact when it will help future tasks." />}</section></>; }

function Conversations({ conversations, open }: { conversations: Conversation[]; open: (id: string) => void }) { return <><PageHeader eyebrow="Persistent context" title="Conversation history" copy="Reopen conversations persisted by the backend." /><section className="panel">{conversations.length ? <div className="record-list">{conversations.map((conversation) => <button className="conversation-record" key={conversation.conversation_id} onClick={() => open(conversation.conversation_id)} type="button"><MessageSquare size={17} /><div><strong>{conversation.title}</strong><small>Updated {formatDate(conversation.updated_at)}</small></div><ChevronRight /></button>)}</div> : <Empty title="No conversations yet" copy="Your completed quick chats will appear here." />}</section></>; }

function Tasks({ tasks, filter, setFilter, search, setSearch, activeTask, cancel, retry, decide }: { tasks: Task[]; filter: string; setFilter: (value: string) => void; search: string; setSearch: (value: string) => void; activeTask: BackgroundTask | null; cancel: (id: string) => void; retry: (task: BackgroundTask) => void; decide: (id: string, decision: "approve" | "reject") => void }) { return <><PageHeader eyebrow="Execution archive" title="Task history" copy="Search stored tasks, review approvals, and inspect the live status of the current background task." />{activeTask && <section className="panel active-task-panel"><BackgroundTaskCard task={activeTask} />{activeTask.approval_status === "pending" ? <><button className="queue-button" onClick={() => decide(activeTask.task_id, "approve")} type="button">Approve task</button><button className="queue-button" onClick={() => decide(activeTask.task_id, "reject")} type="button">Reject task</button></> : null}{activeTask.status === "queued" || activeTask.status === "running" ? <button className="queue-button" onClick={() => cancel(activeTask.task_id)} type="button">Cancel task</button> : null}{activeTask.status === "failed" || activeTask.status === "completed_with_errors" ? <button className="queue-button" onClick={() => retry(activeTask)} type="button">Retry task</button> : null}</section>}<section className="panel"><div className="task-controls"><label><Search size={16} /><input aria-label="Search tasks" onChange={(event) => setSearch(event.target.value)} placeholder="Search task descriptions..." value={search} /></label><select aria-label="Filter task status" onChange={(event) => setFilter(event.target.value)} value={filter}><option value="all">All statuses</option><option value="completed">Completed</option><option value="completed_with_errors">With errors</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option></select></div>{tasks.length ? tasks.map((task) => <TaskRow key={task.task_id} task={task} decide={decide} />) : <Empty title="No matching tasks" copy="Try another search or run a new background task." />}</section></>; }

function SettingsView() { return <><PageHeader eyebrow="Configuration" title="Settings" copy="Current development-session configuration and privacy notes." /><section className="panel settings-list"><div><strong>Backend API</strong><span>Configured through VITE_API_BASE_URL</span></div><div><strong>Identity</strong><span>Browser session ID via X-Session-ID; this is not production authentication.</span></div><div><strong>Persistence</strong><span>PostgreSQL/pgvector is recommended. SQLite fallback is supported for local development.</span></div><div><strong>Real-time monitoring</strong><span>Current backend returns completed task step data synchronously; no fabricated live progress is displayed.</span></div></section></>; }

export default App;
