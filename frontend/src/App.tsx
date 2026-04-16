import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Database,
  Globe,
  LayoutDashboard,
  Loader2,
  MessageCircle,
  MessageSquare,
  Mic,
  MicOff,
  PlusCircle,
  Send,
  Sparkles,
  Target,
  Trash2,
  TrendingUp,
  User,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

declare global {
  interface SpeechRecognitionResultLike {
    transcript: string;
  }

  interface SpeechRecognitionLike {
    lang: string;
    onstart: null | (() => void);
    onend: null | (() => void);
    onerror: null | (() => void);
    onresult: null | ((event: { results: ArrayLike<ArrayLike<SpeechRecognitionResultLike>> }) => void);
    start: () => void;
  }

  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

type MsgStatus = "sending" | "sent" | "delivered";
type MsgSender = "user" | "agent" | "system";

type BackendHistoryMessage = {
  role: string;
  message: string;
  timestamp: string;
  agent_type?: string | null;
  action?: string | null;
  metadata?: Record<string, unknown>;
};

type Message = {
  id: number;
  sender: MsgSender;
  text: string;
  agent?: string;
  targetAgent?: string;
  ts: string;
  status?: MsgStatus;
  metadata?: Record<string, unknown>;
};

type AlertItem = {
  id: number;
  title: string;
  description: string;
  severity: "high" | "medium" | "low";
  source: string;
  resolved: boolean;
};

type Health = {
  status: string;
  database?: string;
  version?: string;
};

type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  lastMessage: string;
  messageCount: number;
};

type RoutingMetadata = {
  original_query?: string;
  sanitized_query?: string;
  agent?: string;
  action?: string;
  agent_description?: string;
  action_description?: string;
  tool_descriptions?: Record<string, string>;
  intent_reasoning?: string;
  params?: Record<string, unknown>;
};

type WebSocketResponse = {
  status: string;
  message?: string;
  thread_id?: string;
  session_id?: string;
  agent?: string;
  action?: string;
  data?: Record<string, unknown>;
  metadata?: RoutingMetadata;
  task_id?: string;
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8000/ws";

let MESSAGE_ID = 0;

const NAV = [
  { id: "conversations", icon: MessageSquare, label: "Chat" },
  { id: "dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { id: "knowledge", icon: BookOpen, label: "Knowledge Base" },
  { id: "research", icon: Globe, label: "Research" },
] as const;

const RESEARCH_CATEGORIES = [
  {
    title: "Competitive Intelligence",
    icon: Target,
    color: "#d93025",
    queries: [
      "Compare our top cloud vendors by service coverage and quality.",
      "Analyze market positioning for managed Kubernetes providers.",
      "Summarize emerging vendor risks in our infrastructure stack.",
    ],
  },
  {
    title: "Market & Industry",
    icon: TrendingUp,
    color: "#1a73e8",
    queries: [
      "List all vendors for different services we have across all category.",
      "Find the best cloud vendor within $50,000 budget.",
      "Show data analytics vendors with strong delivery performance.",
    ],
  },
] as const;

const SUGGESTIONS = [
  "List all vendors for different services we have across all category.",
  "Find the best cloud vendor within $50,000 budget.",
  "Assess vendor Acme Cloud Solutions.",
  "Check SLA compliance for V-001.",
  "Search the knowledge base for cloud hosting contracts.",
];

const AGENT_COLORS: Record<string, string> = {
  vendor_management: "#1a73e8",
  meetings_communication: "#e37400",
  knowledge_base: "#1e8e3e",
};

const AGENT_OPTIONS = [
  { id: "vendor_management", label: "Vendor", description: "Vendors, contracts, SLA, scoring" },
  { id: "meetings_communication", label: "Communication", description: "Meetings, briefs, scheduling" },
  { id: "knowledge_base", label: "Knowledge", description: "Search stored docs and notes" },
] as const;

function nextMessageId(): number {
  MESSAGE_ID += 1;
  return MESSAGE_ID;
}

function toChatSession(raw: Record<string, unknown>): ChatSession {
  return {
    id: String(raw.id ?? ""),
    title: buildConversationTitle(String(raw.last_message ?? "New Chat")),
    createdAt: String(raw.created_at ?? new Date().toISOString()),
    updatedAt: String(raw.updated_at ?? new Date().toISOString()),
    lastMessage: String(raw.last_message ?? ""),
    messageCount: Number(raw.message_count ?? 0),
  };
}

function buildConversationTitle(lastMessage: string): string {
  const cleaned = stripAgentLabel(lastMessage).trim();
  if (!cleaned) return "New Chat";
  return cleaned.length > 42 ? `${cleaned.slice(0, 42)}…` : cleaned;
}

function inferSender(role: string): MsgSender {
  if (role === "user") return "user";
  if (role === "assistant") return "agent";
  return "system";
}

function prettifyAgent(agent?: string | null): string | undefined {
  if (!agent) return undefined;
  return agent.replace(/_/g, " ");
}

function stripAgentLabel(text: string): string {
  return text.replace(/^\[[^\]]+\]\s*/, "").trim();
}

function speechRecognitionCtor(): (new () => SpeechRecognitionLike) | undefined {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function RichText({ text, isUser }: { text: string; isUser: boolean }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let ordered = false;
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let tableLines: string[] = [];

  const flushList = () => {
    if (!listItems.length) return;
    const Tag = ordered ? "ol" : "ul";
    blocks.push(
      <Tag
        key={`list-${blocks.length}`}
        style={{
          margin: "8px 0",
          paddingLeft: 20,
          color: isUser ? "#fff" : "#3c4043",
          lineHeight: 1.6,
        }}
      >
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`} style={{ marginBottom: 4 }}>
            <InlineFormat text={item} isUser={isUser} />
          </li>
        ))}
      </Tag>,
    );
    listItems = [];
    ordered = false;
  };

  const flushCode = () => {
    if (!codeLines.length) return;
    blocks.push(
      <pre
        key={`code-${blocks.length}`}
        style={{
          margin: "10px 0",
          borderRadius: 12,
          padding: "12px 14px",
          overflowX: "auto",
          background: isUser ? "rgba(255,255,255,0.16)" : "#f1f3f4",
          color: isUser ? "#fff" : "#202124",
          fontSize: 12,
          lineHeight: 1.6,
        }}
      >
        <code>{codeLines.join("\n")}</code>
      </pre>,
    );
    codeLines = [];
  };

  const flushTable = () => {
    if (!tableLines.length) return;
    const rows = tableLines.map((line) =>
      line
        .split("|")
        .map((cell) => cell.trim())
        .filter(Boolean),
    );
    const bodyRows = rows.filter(
      (row, index) => !(index === 1 && row.every((cell) => /^:?-{3,}:?$/.test(cell))),
    );
    if (!bodyRows.length) {
      tableLines = [];
      return;
    }
    const header = bodyRows[0];
    const rest = bodyRows.slice(1);
    blocks.push(
      <div key={`table-wrap-${blocks.length}`} style={{ overflowX: "auto", margin: "10px 0" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            borderRadius: 12,
            overflow: "hidden",
            background: isUser ? "rgba(255,255,255,0.08)" : "#f8f9fa",
          }}
        >
          <thead>
            <tr>
              {header.map((cell, index) => (
                <th
                  key={`head-${index}`}
                  style={{
                    textAlign: "left",
                    padding: "10px 12px",
                    fontSize: 12,
                    fontWeight: 700,
                    color: isUser ? "#fff" : "#202124",
                    borderBottom: `1px solid ${isUser ? "rgba(255,255,255,0.18)" : "#e8eaed"}`,
                  }}
                >
                  <InlineFormat text={cell} isUser={isUser} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rest.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    style={{
                      padding: "10px 12px",
                      fontSize: 12,
                      lineHeight: 1.5,
                      color: isUser ? "#fff" : "#3c4043",
                      borderTop: `1px solid ${isUser ? "rgba(255,255,255,0.12)" : "#eceff1"}`,
                    }}
                  >
                    <InlineFormat text={cell} isUser={isUser} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    tableLines = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    if (line.trim().startsWith("```")) {
      flushList();
      flushTable();
      if (inCodeBlock) {
        flushCode();
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    if (line.includes("|") && line.trim().startsWith("|")) {
      flushList();
      tableLines.push(line);
      continue;
    }
    flushTable();

    const unorderedMatch = line.match(/^\s*[-*]\s+(.+)/);
    const orderedMatch = line.match(/^\s*\d+[.)]\s+(.+)/);
    if (unorderedMatch) {
      if (ordered) flushList();
      listItems.push(unorderedMatch[1]);
      continue;
    }
    if (orderedMatch) {
      if (!ordered && listItems.length) flushList();
      ordered = true;
      listItems.push(orderedMatch[1]);
      continue;
    }
    flushList();

    if (!line.trim()) {
      blocks.push(<div key={`spacer-${index}`} style={{ height: 6 }} />);
      continue;
    }

    const h1 = line.match(/^#\s+(.+)/);
    if (h1) {
      blocks.push(
        <h2
          key={`h1-${index}`}
          style={{
            margin: "12px 0 6px",
            fontSize: 18,
            fontWeight: 700,
            color: isUser ? "#fff" : "#202124",
          }}
        >
          <InlineFormat text={h1[1]} isUser={isUser} />
        </h2>,
      );
      continue;
    }

    const h2 = line.match(/^##\s+(.+)/);
    if (h2) {
      blocks.push(
        <h3
          key={`h2-${index}`}
          style={{
            margin: "10px 0 4px",
            fontSize: 14,
            fontWeight: 600,
            color: isUser ? "#fff" : "#202124",
          }}
        >
          <InlineFormat text={h2[1]} isUser={isUser} />
        </h3>,
      );
      continue;
    }

    const h3 = line.match(/^###\s+(.+)/);
    if (h3) {
      blocks.push(
        <h4
          key={`h3-${index}`}
          style={{
            margin: "10px 0 4px",
            fontSize: 13,
            fontWeight: 700,
            color: isUser ? "#fff" : "#202124",
          }}
        >
          <InlineFormat text={h3[1]} isUser={isUser} />
        </h4>,
      );
      continue;
    }

    blocks.push(
      <p key={`p-${index}`} style={{ margin: "3px 0", lineHeight: 1.65 }}>
        <InlineFormat text={line} isUser={isUser} />
      </p>,
    );
  }

  flushList();
  flushTable();
  flushCode();
  return <div>{blocks}</div>;
}

function InlineFormat({ text, isUser }: { text: string; isUser: boolean }) {
  const parts: ReactNode[] = [];
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null = regex.exec(text);
  while (match) {
    if (match.index > lastIndex) {
      parts.push(<span key={`txt-${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>);
    }
    if (match[2]) {
      parts.push(
        <strong key={`b-${match.index}`} style={{ fontWeight: 700 }}>
          {match[2]}
        </strong>,
      );
    } else if (match[3]) {
      parts.push(
        <em key={`i-${match.index}`} style={{ fontStyle: "italic" }}>
          {match[3]}
        </em>,
      );
    } else if (match[4]) {
      parts.push(
        <code
          key={`c-${match.index}`}
          style={{
            borderRadius: 6,
            padding: "2px 6px",
            background: isUser ? "rgba(255,255,255,0.18)" : "#f1f3f4",
            fontFamily: "monospace",
            fontSize: 12,
          }}
        >
          {match[4]}
        </code>,
      );
    }
    lastIndex = match.index + match[0].length;
    match = regex.exec(text);
  }
  if (lastIndex < text.length) {
    parts.push(<span key={`tail-${lastIndex}`}>{text.slice(lastIndex)}</span>);
  }
  return <>{parts.length ? parts : text}</>;
}

function Toast({
  message,
  type,
  onClose,
}: {
  message: string;
  type: "success" | "error";
  onClose: () => void;
}) {
  useEffect(() => {
    const timeout = window.setTimeout(onClose, 4000);
    return () => window.clearTimeout(timeout);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -14 }}
      style={{
        position: "fixed",
        top: 20,
        right: 20,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "12px 18px",
        borderRadius: 40,
        background: type === "success" ? "#1e8e3e" : "#d93025",
        color: "#fff",
        boxShadow: "0 12px 28px rgba(0,0,0,0.12)",
        backdropFilter: "blur(8px)",
      }}
    >
      {type === "success" ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
      <span style={{ fontSize: 14, fontWeight: 500 }}>{message}</span>
    </motion.div>
  );
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [activeTab, setActiveTab] = useState<(typeof NAV)[number]["id"]>("conversations");
  const [pendingApproval, setPendingApproval] = useState<{ taskId: string; prompt: string } | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [backendDown, setBackendDown] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [kbText, setKbText] = useState("");
  const [kbSource, setKbSource] = useState("");
  const [kbLoading, setKbLoading] = useState(false);
  const [lastRouting, setLastRouting] = useState<RoutingMetadata | null>(null);
  const [routingOpen, setRoutingOpen] = useState(false);
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [selectedAgentHint, setSelectedAgentHint] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const activeSessionInfo = useMemo(
    () => sessions.find((session) => session.id === activeSession) ?? null,
    [sessions, activeSession],
  );

  useEffect(() => {
    void loadBootstrapData();
  }, []);

  useEffect(() => {
    if (!activeSession) return;
    setRoutingOpen(false);
    setAgentPickerOpen(false);
    void loadHistory(activeSession);
  }, [activeSession]);

  useEffect(() => {
    if (!activeSession) return;

    const websocket = new WebSocket(`${WS_URL}?session_id=${encodeURIComponent(activeSession)}`);
    wsRef.current = websocket;

    websocket.onopen = () => setConnected(true);
    websocket.onclose = () => setConnected(false);
    websocket.onerror = () => setConnected(false);
    websocket.onmessage = (event) => handleSocketMessage(event.data);

    return () => {
      websocket.close();
    };
  }, [activeSession]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadBootstrapData() {
    try {
      const [healthData, alertData, conversationData] = await Promise.all([
        fetchJson<Health>(`${API_URL}/health`),
        fetchJson<AlertItem[]>(`${API_URL}/agents/alerts`).catch(() => []),
        fetchJson<Record<string, unknown>[]>(`${API_URL}/agents/conversations`).catch(() => []),
      ]);

      setHealth(healthData);
      setBackendDown(false);
      setAlerts(alertData);

      const mappedSessions = conversationData.map(toChatSession);
      if (mappedSessions.length) {
        setSessions(mappedSessions);
        setActiveSession(mappedSessions[0].id);
      } else {
        const thread = await createThread();
        setSessions([thread]);
        setActiveSession(thread.id);
      }
    } catch {
      setBackendDown(true);
      const thread = await createThread().catch(() => null);
      if (thread) {
        setSessions([thread]);
        setActiveSession(thread.id);
      }
    }
  }

  async function createThread(): Promise<ChatSession> {
    const raw = await fetchJson<Record<string, unknown>>(`${API_URL}/agents/threads`, {
      method: "POST",
    });
    return toChatSession(raw);
  }

  async function loadHistory(threadId: string) {
    try {
      const history = await fetchJson<BackendHistoryMessage[]>(
        `${API_URL}/agents/history?thread_id=${encodeURIComponent(threadId)}`,
      );
      const latestAssistantWithRouting = [...history]
        .reverse()
        .find((entry) => entry.role === "assistant" && entry.metadata);
      setLastRouting((latestAssistantWithRouting?.metadata as RoutingMetadata | undefined) ?? null);
      setMessages(
        history.map((entry) => ({
          id: nextMessageId(),
          sender: inferSender(entry.role),
          text: entry.message,
          agent: prettifyAgent(entry.agent_type),
          targetAgent: prettifyAgent((entry.metadata?.agent_hint as string | undefined) ?? null),
          ts: entry.timestamp,
          status: entry.role === "user" ? "delivered" : undefined,
          metadata: entry.metadata,
        })),
      );
    } catch {
      setMessages([]);
    }
  }

  function refreshSessionFromMessage(threadId: string, preview: string) {
    setSessions((previous) =>
      previous.map((session) =>
        session.id === threadId
          ? {
              ...session,
              title: session.title === "New Chat" ? buildConversationTitle(preview) : session.title,
              lastMessage: preview,
              updatedAt: new Date().toISOString(),
              messageCount: session.messageCount + 1,
            }
          : session,
      ),
    );
  }

  function appendMessage(message: Omit<Message, "id">) {
    setMessages((previous) => [...previous, { ...message, id: nextMessageId() }]);
  }

  function replacePendingUserStatus(status: MsgStatus) {
    setMessages((previous) =>
      previous.map((message) =>
        message.sender === "user" && message.status !== "delivered"
          ? { ...message, status }
          : message,
      ),
    );
  }

  function handleSocketMessage(payload: string) {
    setIsThinking(false);
    const parsed: WebSocketResponse =
      typeof payload === "string" ? JSON.parse(payload) : (payload as unknown as WebSocketResponse);

    if (parsed.status === "ERROR") {
      replacePendingUserStatus("delivered");
      appendMessage({
        sender: "system",
        text: parsed.message ?? "Unknown websocket error.",
        ts: new Date().toISOString(),
      });
      return;
    }

    if (parsed.status === "WAIT_FOR_APPROVAL" && parsed.task_id) {
      setPendingApproval({ taskId: parsed.task_id, prompt: parsed.message ?? "Approval required." });
      appendMessage({
        sender: "system",
        text: "Approval required before the workflow can continue.",
        ts: new Date().toISOString(),
      });
      return;
    }

    replacePendingUserStatus("delivered");
    const reply = parsed.message ?? "";
    const threadId = parsed.thread_id ?? activeSession;
    if (parsed.metadata) setLastRouting(parsed.metadata);

    appendMessage({
      sender: "agent",
      text: reply,
      agent: prettifyAgent(parsed.agent),
      ts: new Date().toISOString(),
      metadata: parsed.metadata,
    });
    refreshSessionFromMessage(threadId, reply);
  }

  function sendSocket(message: Record<string, unknown>) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  async function handleSend(text: string) {
    const prompt = text.trim();
    if (!prompt || !activeSession) return;

    appendMessage({
      sender: "user",
      text: prompt,
      targetAgent: prettifyAgent(selectedAgentHint),
      ts: new Date().toISOString(),
      status: "sending",
      metadata: selectedAgentHint ? { agent_hint: selectedAgentHint } : undefined,
    });
    refreshSessionFromMessage(activeSession, prompt);
    setDraft("");
    setIsThinking(true);

    window.setTimeout(() => replacePendingUserStatus("sent"), 250);

    const sent = sendSocket({
      type: "query",
      message: prompt,
      thread_id: activeSession,
      agent_hint: selectedAgentHint,
    });

    if (!sent) {
      try {
        const result = await fetchJson<{
          result: { response: string; metadata: RoutingMetadata };
          conversation_id: string;
        }>(`${API_URL}/agents/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            conversation_id: activeSession,
            agent_hint: selectedAgentHint ?? "",
            context: selectedAgentHint
              ? { user_message_metadata: { agent_hint: selectedAgentHint } }
              : {},
          }),
        });
        handleSocketMessage(
          JSON.stringify({
            status: "SUCCESS",
            message: result.result.response,
            thread_id: result.conversation_id,
            metadata: result.result.metadata,
            agent: result.result.metadata.agent,
            action: result.result.metadata.action,
          }),
        );
      } catch (error) {
        setIsThinking(false);
        appendMessage({
          sender: "system",
          text: error instanceof Error ? error.message : "Failed to send message.",
          ts: new Date().toISOString(),
        });
      }
    }
  }

  async function handleVoice() {
    const Ctor = speechRecognitionCtor();
    if (!Ctor) {
      setToast({ message: "Speech recognition is not supported in this browser.", type: "error" });
      return;
    }
    const recognition = new Ctor();
    recognition.lang = "en-US";
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setDraft(transcript);
      void handleSend(transcript);
      setIsListening(false);
    };
    recognition.start();
  }

  async function handleNewChat() {
    try {
      const thread = await createThread();
      setSessions((previous) => [thread, ...previous]);
      setActiveSession(thread.id);
      setMessages([]);
      setLastRouting(null);
      setSelectedAgentHint(null);
      setAgentPickerOpen(false);
      setRoutingOpen(false);
    } catch {
      setToast({ message: "Failed to create a new chat.", type: "error" });
    }
  }

  async function handleDeleteChat(threadId: string) {
    try {
      await fetchJson(`${API_URL}/agents/conversations/${threadId}`, { method: "DELETE" });
      const updated = sessions.filter((session) => session.id !== threadId);
      setSessions(updated);
      if (activeSession === threadId) {
        if (updated.length) {
          setActiveSession(updated[0].id);
        } else {
          await handleNewChat();
        }
      }
    } catch {
      setToast({ message: "Failed to delete chat.", type: "error" });
    }
  }

  async function handleKbSubmit() {
    if (!kbText.trim()) return;
    setKbLoading(true);
    try {
      const docId = globalThis.crypto?.randomUUID?.() ?? `doc-${Date.now()}`;
      await fetchJson(`${API_URL}/kb/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection: "manual_uploads",
          doc_id: docId,
          content: kbText.trim(),
          metadata: { source_description: kbSource || "Manual upload" },
        }),
      });
      setToast({ message: "Knowledge stored successfully.", type: "success" });
      setKbText("");
      setKbSource("");
    } catch {
      setToast({ message: "Failed to store knowledge.", type: "error" });
    } finally {
      setKbLoading(false);
    }
  }

  const mainPanel = useMemo(() => {
    if (activeTab === "dashboard") return renderDashboard(alerts, health, setActiveTab, handleSend);
    if (activeTab === "knowledge") {
      return renderKnowledge(kbText, kbSource, kbLoading, setKbText, setKbSource, handleKbSubmit);
    }
    if (activeTab === "research") return renderResearch(handleSend, setActiveTab);
    return null;
  }, [activeTab, alerts, health, kbText, kbSource, kbLoading]);

  return (
    <div style={appShellStyle}>
      <AnimatePresence>
        {toast ? (
          <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
        ) : null}
      </AnimatePresence>

      <aside style={sidebarStyle}>
        <div style={sidebarHeaderStyle}>
          <div style={logoBadgeStyle}>
            <Sparkles size={18} color="#1a73e8" />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#202124", letterSpacing: "-0.01em" }}>
              PilotH
            </div>
            <div style={{ fontSize: 11, color: "#5f6368", letterSpacing: "0.02em" }}>
              Multi‑Agent Console
            </div>
          </div>
        </div>

        <button style={primaryPillButton} onClick={() => void handleNewChat()}>
          <PlusCircle size={18} />
          New chat
        </button>

        <nav style={navContainerStyle}>
          {NAV.map((item) => (
            <button
              key={item.id}
              style={{
                ...navButtonStyle,
                ...(activeTab === item.id ? activeNavButtonStyle : {}),
              }}
              onClick={() => setActiveTab(item.id)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {activeTab === item.id ? <ChevronRight size={14} style={{ marginLeft: "auto" }} /> : null}
            </button>
          ))}
        </nav>

        <div style={sessionsContainerStyle} className="hide-scrollbar">
          <div style={sectionLabelStyle}>Recent chats</div>
          {sessions.map((session) => (
            <div
              key={session.id}
              style={{
                ...sessionCardStyle,
                ...(session.id === activeSession ? activeSessionCardStyle : {}),
              }}
            >
              <button
                style={sessionButtonStyle}
                onClick={() => {
                  setActiveSession(session.id);
                  setActiveTab("conversations");
                }}
              >
                <MessageCircle size={15} />
                <div style={{ minWidth: 0, flex: 1, textAlign: "left" }}>
                  <div style={sessionTitleStyle}>{session.title}</div>
                  <div style={sessionTimestampStyle}>
                    {new Date(session.updatedAt).toLocaleString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
              </button>
              <button style={trashButtonStyle} onClick={() => void handleDeleteChat(session.id)}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "auto" }}>
          <button style={statusToggleStyle} onClick={() => setStatusOpen((open) => !open)}>
            {statusOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            System status
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: 999,
                marginLeft: "auto",
                background: connected ? "#1e8e3e" : "#d93025",
                boxShadow: `0 0 0 2px ${connected ? "#e6f4ea" : "#fce8e6"}`,
              }}
            />
          </button>
          {statusOpen ? (
            <div style={statusCardStyle}>
              <StatusLine label="Connection" value={connected ? "Live" : "Offline"} />
              <StatusLine label="Database" value={health?.database ?? "unknown"} />
              <StatusLine label="Version" value={health?.version ?? "1.0.0"} />
              <StatusLine label="Messages" value={String(activeSessionInfo?.messageCount ?? 0)} />
            </div>
          ) : null}
        </div>
      </aside>

      <main style={mainStyle}>
        <header style={headerStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1 style={pageTitleStyle}>
              {NAV.find((item) => item.id === activeTab)?.label ?? activeTab}
            </h1>
            {isThinking ? (
              <div style={thinkingBadgeStyle}>
                <Loader2 size={12} className="spin" />
                Thinking...
              </div>
            ) : null}
          </div>
          <div style={connectionBadgeStyle(connected)}>
            {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
            {connected ? "Connected" : "Offline"}
          </div>
        </header>

        {backendDown ? (
          <div style={backendWarningStyle}>
            <AlertTriangle size={16} />
            Backend is offline or still starting. Some actions may fail until it is available.
          </div>
        ) : null}

        <AnimatePresence>
          {pendingApproval ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={modalBackdropStyle}
            >
              <motion.div
                initial={{ scale: 0.96, y: 10 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.96, y: 10 }}
                style={modalCardStyle}
              >
                <div style={modalHeaderStyle}>
                  <div style={warningIconWrapStyle}>
                    <AlertTriangle size={18} color="#f9ab00" />
                  </div>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 600 }}>Approval Required</div>
                    <div style={{ fontSize: 13, color: "#5f6368" }}>
                      Review the request before continuing.
                    </div>
                  </div>
                </div>
                <pre style={modalPromptStyle}>{pendingApproval.prompt}</pre>
                <div style={modalActionsStyle}>
                  <button
                    style={secondaryActionButton}
                    onClick={() => {
                      sendSocket({ type: "deny", task_id: pendingApproval.taskId });
                      setPendingApproval(null);
                    }}
                  >
                    <XCircle size={16} />
                    Deny
                  </button>
                  <button
                    style={primaryActionButton}
                    onClick={() => {
                      sendSocket({ type: "approve", task_id: pendingApproval.taskId });
                      setPendingApproval(null);
                    }}
                  >
                    <CheckCircle2 size={16} />
                    Approve
                  </button>
                </div>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {activeTab === "conversations" ? (
          <div style={chatLayoutStyle}>
            <section style={chatColumnStyle}>
              <div style={messagesPaneStyle} className="hide-scrollbar">
                {messages.length ? (
                  messages.map((message) => <MessageRow key={message.id} msg={message} />)
                ) : (
                  <EmptyState onPickSuggestion={handleSend} />
                )}
                <div ref={endRef} />
              </div>
              {selectedAgentHint ? (
                <div style={selectedAgentBarStyle}>
                  <span style={selectedAgentLabelStyle}>Routing to</span>
                  <span style={agentHintChipStyle(selectedAgentHint)}>
                    {AGENT_OPTIONS.find((option) => option.id === selectedAgentHint)?.label ?? selectedAgentHint}
                  </span>
                  <button
                    type="button"
                    style={clearAgentHintButtonStyle}
                    onClick={() => setSelectedAgentHint(null)}
                  >
                    <XCircle size={14} />
                  </button>
                </div>
              ) : null}
              <form
                style={composerWrapStyle}
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleSend(draft);
                }}
              >
                <div style={agentPickerWrapStyle}>
                  <button
                    type="button"
                    style={agentPickerButtonStyle}
                    onClick={() => setAgentPickerOpen((open) => !open)}
                  >
                    <PlusCircle size={16} />
                  </button>
                  <AnimatePresence>
                    {agentPickerOpen ? (
                      <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 6 }}
                        style={agentPickerMenuStyle}
                      >
                        {AGENT_OPTIONS.map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            style={agentPickerItemStyle(selectedAgentHint === option.id)}
                            onClick={() => {
                              setSelectedAgentHint(option.id);
                              setAgentPickerOpen(false);
                            }}
                          >
                            <span style={agentPickerItemTitleStyle}>{option.label}</span>
                            <span style={agentPickerItemDescriptionStyle}>{option.description}</span>
                          </button>
                        ))}
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Message your agents..."
                  style={composerInputStyle}
                />
                <button type="button" style={iconCircleButton(isListening)} onClick={() => void handleVoice()}>
                  {isListening ? <Mic size={18} color="#fff" /> : <MicOff size={18} color="#5f6368" />}
                </button>
                <button type="submit" style={sendButtonStyle} disabled={!draft.trim()}>
                  <Send size={16} />
                </button>
              </form>
            </section>

            <aside style={detailsPanelStyle}>
              <div style={detailsCardStyle}>
                <div style={detailsTitleStyle}>Thread details</div>
                <DetailRow label="Thread" value={activeSession || "Not selected"} mono />
                <DetailRow label="Messages" value={String(activeSessionInfo?.messageCount ?? messages.length)} />
                <DetailRow label="Updated" value={activeSessionInfo ? new Date(activeSessionInfo.updatedAt).toLocaleString() : "-"} />
              </div>

              <div style={detailsCardStyle}>
                <button
                  type="button"
                  style={routingToggleButtonStyle}
                  onClick={() => setRoutingOpen((open) => !open)}
                >
                  <span style={detailsTitleStyle}>Latest routing</span>
                  {routingOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <AnimatePresence initial={false}>
                  {routingOpen ? (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      style={{ overflow: "hidden" }}
                    >
                      {lastRouting ? (
                        <>
                          <DetailRow label="Original query" value={lastRouting.original_query ?? "-"} />
                          <DetailRow label="Sanitized query" value={lastRouting.sanitized_query ?? "-"} />
                          <DetailRow label="Agent" value={lastRouting.agent ?? "-"} />
                          <DetailRow label="Action" value={lastRouting.action ?? "-"} />
                          <DetailRow label="Agent desc" value={lastRouting.agent_description ?? "-"} />
                          <DetailRow label="Action desc" value={lastRouting.action_description ?? "-"} />
                          <div style={{ marginTop: 16 }}>
                            <div style={detailsLabelStyle}>Available tools</div>
                            <div style={toolsGridStyle}>
                              {Object.entries(lastRouting.tool_descriptions ?? {}).map(([tool, description]) => (
                                <div key={tool} style={toolCardStyle}>
                                  <div style={{ fontSize: 12, fontWeight: 600, color: "#202124" }}>{tool}</div>
                                  <div style={{ fontSize: 12, color: "#5f6368", lineHeight: 1.5 }}>{description}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </>
                      ) : (
                        <div style={emptyRoutingStyle}>
                          Send a message to see the selected agent, chosen action, and tool descriptions.
                        </div>
                      )}
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
            </aside>
          </div>
        ) : (
          <div style={{ flex: 1, overflow: "auto" }}>{mainPanel}</div>
        )}
      </main>
    </div>
  );
}

function EmptyState({ onPickSuggestion }: { onPickSuggestion: (text: string) => void }) {
  return (
    <div style={emptyStateWrapStyle}>
      <div style={logoBadgeStyle}>
        <MessageSquare size={28} color="#1a73e8" />
      </div>
      <div style={emptyStateTitleStyle}>How can I help today?</div>
      <div style={emptyStateSubtitleStyle}>Ask the orchestrator to route work to the right agent.</div>
      <div style={suggestionsContainerStyle}>
        {SUGGESTIONS.map((suggestion) => (
          <button key={suggestion} style={suggestionButtonStyle} onClick={() => onPickSuggestion(suggestion)}>
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function renderDashboard(
  alerts: AlertItem[],
  health: Health | null,
  setActiveTab: (tab: (typeof NAV)[number]["id"]) => void,
  handleSend: (text: string) => Promise<void>,
) {
  return (
    <div style={contentWrapStyle}>
      <div style={dashboardGridStyle}>
        <div style={{ ...contentCardStyle, gridColumn: "span 2" }}>
          <div style={cardHeaderStyle}>
            <span style={cardHeaderTitleStyle}>
              <AlertTriangle size={16} color="#d93025" />
              Strategic alerts
            </span>
            <span style={alertCountStyle}>{alerts.length} active</span>
          </div>
          <div style={alertsContainerStyle}>
            {alerts.length ? (
              alerts.map((alert) => (
                <div key={alert.id} style={alertCardStyle(alert.severity)}>
                  <div style={alertTitleStyle}>{alert.title}</div>
                  <div style={alertDescriptionStyle}>{alert.description}</div>
                  <div style={alertSourceStyle}>{alert.source}</div>
                </div>
              ))
            ) : (
              <div style={noAlertsStyle}>No active alerts.</div>
            )}
          </div>
        </div>

        <div style={contentCardStyle}>
          <div style={cardHeaderStyle}>System overview</div>
          <div style={systemOverviewGridStyle}>
            <StatusLine label="Status" value={health?.status ?? "unknown"} />
            <StatusLine label="Database" value={health?.database ?? "unknown"} />
            <StatusLine label="Version" value={health?.version ?? "1.0.0"} />
          </div>
        </div>

        <div style={{ ...contentCardStyle, gridColumn: "span 3" }}>
          <div style={cardHeaderStyle}>Quick actions</div>
          <div style={quickActionsContainerStyle}>
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                style={suggestionButtonStyle}
                onClick={() => {
                  setActiveTab("conversations");
                  void handleSend(suggestion);
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function renderKnowledge(
  kbText: string,
  kbSource: string,
  kbLoading: boolean,
  setKbText: (value: string) => void,
  setKbSource: (value: string) => void,
  handleKbSubmit: () => Promise<void>,
) {
  return (
    <div style={contentWrapStyle}>
      <div style={singleColumnCardStyle}>
        <div style={cardHeaderStyle}>
          <span style={cardHeaderTitleStyle}>
            <Database size={16} color="#1a73e8" />
            Knowledge base
          </span>
        </div>
        <label style={fieldLabelStyle}>Knowledge content</label>
        <textarea
          value={kbText}
          onChange={(event) => setKbText(event.target.value)}
          rows={8}
          style={textareaStyle}
          placeholder="Paste policies, notes, or vendor context here..."
        />
        <label style={fieldLabelStyle}>Source label</label>
        <input
          value={kbSource}
          onChange={(event) => setKbSource(event.target.value)}
          style={textInputStyle}
          placeholder="e.g. Q2 vendor briefing"
        />
        <div style={knowledgeFooterStyle}>
          <div style={wordCountStyle}>
            {kbText.trim() ? `${kbText.trim().split(/\s+/).length} words` : "No content yet"}
          </div>
          <button style={primaryActionButton} onClick={() => void handleKbSubmit()} disabled={kbLoading}>
            {kbLoading ? <Loader2 size={16} className="spin" /> : <PlusCircle size={16} />}
            {kbLoading ? "Storing..." : "Add to knowledge base"}
          </button>
        </div>
      </div>
    </div>
  );
}

function renderResearch(
  handleSend: (text: string) => Promise<void>,
  setActiveTab: (tab: (typeof NAV)[number]["id"]) => void,
) {
  return (
    <div style={contentWrapStyle}>
      <div style={researchGridStyle}>
        {RESEARCH_CATEGORIES.map((category) => (
          <div key={category.title} style={contentCardStyle}>
            <div style={cardHeaderStyle}>
              <span style={cardHeaderTitleStyle}>
                <category.icon size={16} color={category.color} />
                {category.title}
              </span>
            </div>
            <div style={researchQueriesContainerStyle}>
              {category.queries.map((query) => (
                <button
                  key={query}
                  style={researchButtonStyle}
                  onClick={() => {
                    setActiveTab("conversations");
                    void handleSend(query);
                  }}
                >
                  {query}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MessageRow({ msg }: { msg: Message }) {
  const isUser = msg.sender === "user";
  const isSystem = msg.sender === "system";
  const bubbleColor = isUser ? "#1a73e8" : "#ffffff";
  const textColor = isUser ? "#fff" : "#202124";
  const agentKey = (msg.metadata?.agent as string | undefined) ?? msg.agent?.replace(/\s+/g, "_");
  const agentColor = AGENT_COLORS[agentKey ?? ""] ?? "#1a73e8";
  const toolDescriptions = (msg.metadata?.tool_descriptions as Record<string, string> | undefined) ?? {};

  if (isSystem) {
    return (
      <div style={{ display: "flex", justifyContent: "center" }}>
        <div style={systemMessageStyle}>{msg.text}</div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-end",
        gap: 12,
      }}
    >
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: 999,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: isUser ? "#1a73e8" : "#f1f3f4",
          boxShadow: isUser ? "0 2px 8px rgba(26,115,232,0.2)" : "none",
        }}
      >
        {isUser ? <User size={16} color="#fff" /> : <Bot size={16} color={agentColor} />}
      </div>

      <div style={{ display: "grid", gap: 6, maxWidth: "78%" }}>
        <div style={messageSenderStyle(isUser, agentColor)}>
          {isUser ? "You" : msg.agent ?? "Agent"}
        </div>
        {isUser && msg.targetAgent ? (
          <div style={messageTargetWrapStyle}>
            <span style={agentHintChipStyle(msg.metadata?.agent_hint as string ?? msg.targetAgent)}>
              {msg.targetAgent}
            </span>
          </div>
        ) : null}
        <div
          style={{
            borderRadius: 20,
            padding: "12px 16px",
            background: bubbleColor,
            color: textColor,
            boxShadow: isUser
              ? "0 4px 12px rgba(26,115,232,0.15)"
              : "0 2px 8px rgba(0,0,0,0.04)",
          }}
        >
          <RichText text={stripAgentLabel(msg.text)} isUser={isUser} />
          {!isUser && (msg.metadata?.agent_description || msg.metadata?.action_description) ? (
            <div style={routingInfoStyle}>
              <div style={routingHeaderStyle}>Routing</div>
              <div style={routingDescriptionStyle}>
                {(msg.metadata?.agent_description as string | undefined) ?? ""}
              </div>
              <div style={routingDescriptionStyle}>
                {(msg.metadata?.action_description as string | undefined) ?? ""}
              </div>
              {Object.keys(toolDescriptions).length ? (
                <div style={messageToolsGridStyle}>
                  {Object.entries(toolDescriptions).map(([tool, description]) => (
                    <div key={tool} style={messageToolCardStyle}>
                      <div style={{ fontSize: 11, fontWeight: 600 }}>{tool}</div>
                      <div style={{ fontSize: 11, color: "#5f6368" }}>{description}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        <div style={messageMetaStyle}>
          {new Date(msg.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          {isUser ? <StatusIcon status={msg.status ?? "delivered"} /> : null}
        </div>
      </div>
    </motion.div>
  );
}

function StatusIcon({ status }: { status: MsgStatus }) {
  if (status === "sending") return <Clock size={10} color="#80868b" />;
  if (status === "sent") return <Check size={11} color="#80868b" />;
  return <CheckCheck size={11} color="#1a73e8" />;
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={statusLineStyle}>
      <span style={statusLineLabelStyle}>{label}</span>
      <span style={statusLineValueStyle}>{value}</span>
    </div>
  );
}

function DetailRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={detailRowStyle}>
      <div style={detailsLabelStyle}>{label}</div>
      <div style={detailValueStyle(mono)}>{value}</div>
    </div>
  );
}

// ------------------------------------------------------------
// STYLES – PREMIUM, MINIMAL, NO HARD LINES
// ------------------------------------------------------------

const appShellStyle: CSSProperties = {
  display: "flex",
  height: "100vh",
  width: "100vw",
  overflow: "hidden",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  background: "#fafbfc",
};

const sidebarStyle: CSSProperties = {
  width: 280,
  background: "#ffffff",
  padding: "20px 16px",
  display: "flex",
  flexDirection: "column",
  gap: 8,
  boxShadow: "1px 0 0 rgba(0,0,0,0.02), 4px 0 12px rgba(0,0,0,0.02)",
};

const sidebarHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "0 6px 20px",
};

const logoBadgeStyle: CSSProperties = {
  width: 40,
  height: 40,
  borderRadius: 14,
  background: "#e8f0fe",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 2px 6px rgba(26,115,232,0.08)",
};

const primaryPillButton: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "12px 16px",
  borderRadius: 40,
  border: "none",
  background: "#f1f3f4",
  color: "#202124",
  fontWeight: 600,
  fontSize: 14,
  boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
  transition: "background 0.15s",
  cursor: "pointer",
};

const navContainerStyle: CSSProperties = {
  marginTop: 8,
  display: "grid",
  gap: 2,
};

const navButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  width: "100%",
  padding: "12px 14px",
  borderRadius: 14,
  color: "#5f6368",
  fontWeight: 500,
  fontSize: 14,
  background: "transparent",
  border: "none",
  cursor: "pointer",
  transition: "background 0.15s, color 0.15s",
};

const activeNavButtonStyle: CSSProperties = {
  background: "#e8f0fe",
  color: "#1a73e8",
};

const sessionsContainerStyle: CSSProperties = {
  marginTop: 16,
  paddingTop: 8,
  overflow: "auto",
  flex: 1,
  minHeight: 0,
};

const sectionLabelStyle: CSSProperties = {
  padding: "8px 12px",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "#80868b",
  fontWeight: 600,
};

const sessionCardStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  borderRadius: 14,
  padding: "4px 6px",
  marginBottom: 2,
  transition: "background 0.15s",
};

const activeSessionCardStyle: CSSProperties = {
  background: "#e8f0fe",
};

const sessionButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  flex: 1,
  minWidth: 0,
  padding: "8px 6px",
  borderRadius: 12,
  background: "transparent",
  border: "none",
  cursor: "pointer",
  textAlign: "left",
};

const sessionTitleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 500,
  color: "#202124",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const sessionTimestampStyle: CSSProperties = {
  fontSize: 10,
  color: "#80868b",
  marginTop: 2,
};

const trashButtonStyle: CSSProperties = {
  padding: 6,
  borderRadius: 10,
  color: "#80868b",
  background: "transparent",
  border: "none",
  cursor: "pointer",
  opacity: 0.7,
  transition: "opacity 0.15s, background 0.15s",
};

const statusToggleStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  width: "100%",
  padding: "12px 14px",
  borderRadius: 14,
  background: "#f8f9fa",
  color: "#5f6368",
  fontWeight: 500,
  fontSize: 13,
  border: "none",
  cursor: "pointer",
  transition: "background 0.15s",
};

const statusCardStyle: CSSProperties = {
  marginTop: 8,
  padding: 16,
  borderRadius: 18,
  background: "#ffffff",
  boxShadow: "0 8px 20px rgba(0,0,0,0.04)",
  display: "grid",
  gap: 12,
};

const mainStyle: CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
  background: "#fafbfc",
};

const headerStyle: CSSProperties = {
  height: 64,
  background: "#ffffff",
  padding: "0 24px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  boxShadow: "0 1px 0 rgba(0,0,0,0.02), 0 4px 8px rgba(0,0,0,0.02)",
};

const pageTitleStyle: CSSProperties = {
  fontSize: 18,
  fontWeight: 600,
  color: "#202124",
  textTransform: "capitalize",
  letterSpacing: "-0.01em",
};

const thinkingBadgeStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 12,
  fontWeight: 500,
  color: "#1a73e8",
  background: "#e8f0fe",
  borderRadius: 40,
  padding: "6px 12px",
};

const connectionBadgeStyle = (connected: boolean): CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: 6,
  borderRadius: 40,
  padding: "6px 12px",
  fontSize: 12,
  fontWeight: 500,
  color: connected ? "#1e8e3e" : "#d93025",
  background: connected ? "#e6f4ea" : "#fce8e6",
  boxShadow: "0 2px 4px rgba(0,0,0,0.02)",
});

const backendWarningStyle: CSSProperties = {
  margin: "12px 20px 0",
  borderRadius: 40,
  background: "#fce8e6",
  color: "#d93025",
  display: "flex",
  gap: 10,
  alignItems: "center",
  padding: "12px 18px",
  fontSize: 13,
  fontWeight: 500,
};

const modalBackdropStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(32,33,36,0.3)",
  backdropFilter: "blur(3px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 60,
};

const modalCardStyle: CSSProperties = {
  width: "min(520px, 92vw)",
  borderRadius: 28,
  background: "#fff",
  padding: 28,
  boxShadow: "0 28px 48px rgba(0,0,0,0.12)",
};

const modalHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 16,
  marginBottom: 20,
};

const warningIconWrapStyle: CSSProperties = {
  width: 44,
  height: 44,
  borderRadius: 999,
  background: "#fef7e0",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const modalPromptStyle: CSSProperties = {
  borderRadius: 20,
  background: "#f8f9fa",
  padding: 18,
  whiteSpace: "pre-wrap",
  fontSize: 13,
  lineHeight: 1.6,
  marginBottom: 24,
  border: "none",
};

const modalActionsStyle: CSSProperties = {
  display: "flex",
  gap: 12,
};

const secondaryActionButton: CSSProperties = {
  flex: 1,
  borderRadius: 40,
  border: "none",
  padding: "14px 18px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontWeight: 600,
  fontSize: 14,
  color: "#5f6368",
  background: "#f1f3f4",
  cursor: "pointer",
  transition: "background 0.15s",
};

const primaryActionButton: CSSProperties = {
  flex: 1,
  borderRadius: 40,
  border: "none",
  padding: "14px 18px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontWeight: 600,
  fontSize: 14,
  color: "#fff",
  background: "#1a73e8",
  boxShadow: "0 4px 12px rgba(26,115,232,0.2)",
  cursor: "pointer",
  transition: "background 0.15s, box-shadow 0.15s",
};

const chatLayoutStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 380px",
  gap: 20,
  padding: 20,
};

const chatColumnStyle: CSSProperties = {
  minWidth: 0,
  display: "flex",
  flexDirection: "column",
  gap: 16,
  minHeight: 0,
};

const messagesPaneStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflow: "auto",
  display: "grid",
  gap: 18,
  paddingRight: 6,
  paddingBottom: 8,
};

const composerWrapStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: 8,
  borderRadius: 40,
  background: "#ffffff",
  boxShadow: "0 8px 24px rgba(0,0,0,0.06)",
  border: "none",
  position: "sticky",
  bottom: 0,
  zIndex: 4,
};

const composerInputStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  border: "none",
  outline: "none",
  background: "transparent",
  padding: "12px 16px",
  color: "#202124",
  fontSize: 15,
};

const iconCircleButton = (active: boolean): CSSProperties => ({
  width: 44,
  height: 44,
  borderRadius: 999,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: active ? "#d93025" : "#f1f3f4",
  border: "none",
  cursor: "pointer",
  transition: "background 0.15s",
});

const sendButtonStyle: CSSProperties = {
  width: 44,
  height: 44,
  borderRadius: 999,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#1a73e8",
  color: "#fff",
  border: "none",
  cursor: "pointer",
  boxShadow: "0 2px 8px rgba(26,115,232,0.2)",
  transition: "background 0.15s, box-shadow 0.15s",
};

const detailsPanelStyle: CSSProperties = {
  minWidth: 0,
  display: "grid",
  alignContent: "start",
  gap: 16,
  minHeight: 0,
  overflow: "auto",
};

const detailsCardStyle: CSSProperties = {
  borderRadius: 24,
  background: "#ffffff",
  padding: 20,
  boxShadow: "0 4px 16px rgba(0,0,0,0.04)",
};

const detailsTitleStyle: CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#202124",
  marginBottom: 16,
  letterSpacing: "-0.01em",
};

const detailsLabelStyle: CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  fontWeight: 600,
  color: "#80868b",
  marginBottom: 4,
};

const toolCardStyle: CSSProperties = {
  borderRadius: 16,
  background: "#f8f9fa",
  padding: 14,
  border: "none",
};

const selectedAgentBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "0 8px",
  marginTop: -4,
};

const selectedAgentLabelStyle: CSSProperties = {
  fontSize: 12,
  color: "#80868b",
  fontWeight: 600,
};

const clearAgentHintButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#80868b",
  background: "transparent",
  border: "none",
  padding: 0,
};

const agentPickerWrapStyle: CSSProperties = {
  position: "relative",
  flexShrink: 0,
};

const agentPickerButtonStyle: CSSProperties = {
  width: 44,
  height: 44,
  borderRadius: 999,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#f1f3f4",
  color: "#5f6368",
  border: "none",
};

const agentPickerMenuStyle: CSSProperties = {
  position: "absolute",
  left: 0,
  bottom: "calc(100% + 10px)",
  width: 260,
  borderRadius: 20,
  background: "#ffffff",
  boxShadow: "0 18px 40px rgba(0,0,0,0.12)",
  padding: 8,
  display: "grid",
  gap: 6,
  zIndex: 10,
};

const agentPickerItemStyle = (active: boolean): CSSProperties => ({
  display: "grid",
  gap: 4,
  textAlign: "left",
  padding: "10px 12px",
  borderRadius: 14,
  background: active ? "#e8f0fe" : "#ffffff",
  color: active ? "#1a73e8" : "#202124",
  border: "none",
});

const agentPickerItemTitleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
};

const agentPickerItemDescriptionStyle: CSSProperties = {
  fontSize: 12,
  color: "#5f6368",
  lineHeight: 1.45,
};

const routingToggleButtonStyle: CSSProperties = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
  background: "transparent",
  border: "none",
  padding: 0,
};

const messageTargetWrapStyle: CSSProperties = {
  display: "flex",
};

const agentHintChipStyle = (agentId: string): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  borderRadius: 999,
  padding: "5px 10px",
  background: `${AGENT_COLORS[agentId] ?? "#1a73e8"}18`,
  color: AGENT_COLORS[agentId] ?? "#1a73e8",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
});

const emptyStateWrapStyle: CSSProperties = {
  minHeight: "70vh",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 12,
  textAlign: "center",
  padding: 20,
};

const emptyStateTitleStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 600,
  color: "#202124",
  letterSpacing: "-0.01em",
};

const emptyStateSubtitleStyle: CSSProperties = {
  fontSize: 15,
  color: "#5f6368",
  maxWidth: 460,
};

const suggestionsContainerStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 10,
  justifyContent: "center",
  marginTop: 20,
  maxWidth: 700,
};

const suggestionButtonStyle: CSSProperties = {
  borderRadius: 40,
  border: "none",
  padding: "12px 18px",
  background: "#ffffff",
  color: "#1a73e8",
  fontWeight: 500,
  fontSize: 13,
  boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
  cursor: "pointer",
  transition: "box-shadow 0.15s, background 0.15s",
};

const systemMessageStyle: CSSProperties = {
  maxWidth: 520,
  borderRadius: 40,
  background: "#fef7e0",
  color: "#7c6d22",
  fontSize: 13,
  lineHeight: 1.6,
  padding: "10px 18px",
  border: "none",
};

const routingInfoStyle: CSSProperties = {
  marginTop: 16,
  paddingTop: 12,
  borderTop: "1px solid rgba(0,0,0,0.04)",
};

const routingHeaderStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: "#5f6368",
  marginBottom: 6,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const routingDescriptionStyle: CSSProperties = {
  fontSize: 12,
  color: "#5f6368",
  lineHeight: 1.5,
};

const messageToolsGridStyle: CSSProperties = {
  marginTop: 12,
  display: "grid",
  gap: 8,
};

const messageToolCardStyle: CSSProperties = {
  borderRadius: 12,
  background: "#f8f9fa",
  padding: 10,
  border: "none",
};

const messageSenderStyle = (isUser: boolean, agentColor: string): CSSProperties => ({
  fontSize: 11,
  fontWeight: 600,
  color: isUser ? "#1a73e8" : agentColor,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginLeft: 4,
});

const messageMetaStyle: CSSProperties = {
  fontSize: 10,
  color: "#80868b",
  display: "flex",
  alignItems: "center",
  gap: 6,
  marginLeft: 4,
};

const statusLineStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  fontSize: 13,
};

const statusLineLabelStyle: CSSProperties = {
  color: "#5f6368",
};

const statusLineValueStyle: CSSProperties = {
  color: "#202124",
  maxWidth: 180,
  textAlign: "right",
  overflow: "hidden",
  textOverflow: "ellipsis",
  fontWeight: 500,
};

const detailRowStyle: CSSProperties = {
  marginTop: 12,
};

const detailValueStyle = (mono: boolean): CSSProperties => ({
  fontSize: 13,
  color: "#202124",
  lineHeight: 1.5,
  fontFamily: mono ? "monospace" : "inherit",
  wordBreak: "break-word",
});

const contentWrapStyle: CSSProperties = {
  padding: 24,
};

const dashboardGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: 20,
};

const contentCardStyle: CSSProperties = {
  borderRadius: 24,
  background: "#ffffff",
  padding: 24,
  boxShadow: "0 4px 20px rgba(0,0,0,0.03)",
};

const singleColumnCardStyle: CSSProperties = {
  ...contentCardStyle,
  maxWidth: 820,
  margin: "0 auto",
};

const cardHeaderStyle: CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#202124",
  marginBottom: 20,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
};

const cardHeaderTitleStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
};

const alertCountStyle: CSSProperties = {
  color: "#5f6368",
  fontSize: 13,
  fontWeight: 500,
};

const alertsContainerStyle: CSSProperties = {
  display: "grid",
  gap: 12,
};

const alertCardStyle = (severity: AlertItem["severity"]): CSSProperties => ({
  borderRadius: 20,
  padding: 18,
  borderLeft: `4px solid ${
    severity === "high" ? "#d93025" : severity === "medium" ? "#f9ab00" : "#1e8e3e"
  }`,
  background: "#fafbfc",
  boxShadow: "0 2px 8px rgba(0,0,0,0.02)",
  display: "grid",
  gap: 8,
});

const alertTitleStyle: CSSProperties = {
  fontWeight: 600,
  color: "#202124",
};

const alertDescriptionStyle: CSSProperties = {
  color: "#5f6368",
  fontSize: 13,
  lineHeight: 1.5,
};

const alertSourceStyle: CSSProperties = {
  color: "#80868b",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.03em",
};

const noAlertsStyle: CSSProperties = {
  color: "#5f6368",
  fontSize: 14,
  padding: "12px 0",
};

const systemOverviewGridStyle: CSSProperties = {
  display: "grid",
  gap: 14,
};

const quickActionsContainerStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 10,
};

const fieldLabelStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  marginBottom: 8,
  color: "#202124",
};

const textareaStyle: CSSProperties = {
  width: "100%",
  borderRadius: 18,
  border: "none",
  background: "#f8f9fa",
  padding: 16,
  resize: "vertical",
  minHeight: 180,
  color: "#202124",
  fontSize: 14,
  marginBottom: 20,
  outline: "none",
  boxShadow: "inset 0 1px 3px rgba(0,0,0,0.02)",
};

const textInputStyle: CSSProperties = {
  width: "100%",
  borderRadius: 18,
  border: "none",
  background: "#f8f9fa",
  padding: "14px 16px",
  color: "#202124",
  fontSize: 14,
  outline: "none",
  boxShadow: "inset 0 1px 3px rgba(0,0,0,0.02)",
};

const knowledgeFooterStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginTop: 20,
};

const wordCountStyle: CSSProperties = {
  fontSize: 12,
  color: "#80868b",
};

const researchGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
  gap: 20,
};

const researchQueriesContainerStyle: CSSProperties = {
  display: "grid",
  gap: 10,
};

const researchButtonStyle: CSSProperties = {
  textAlign: "left",
  borderRadius: 18,
  border: "none",
  background: "#f8f9fa",
  padding: "14px 18px",
  color: "#202124",
  fontSize: 13,
  fontWeight: 500,
  lineHeight: 1.5,
  cursor: "pointer",
  transition: "background 0.15s, box-shadow 0.15s",
  boxShadow: "0 1px 2px rgba(0,0,0,0.02)",
};

const emptyRoutingStyle: CSSProperties = {
  fontSize: 13,
  color: "#5f6368",
  lineHeight: 1.6,
};

const toolsGridStyle: CSSProperties = {
  display: "grid",
  gap: 10,
  marginTop: 8,
};

// Global spinner animation
const styleSheet = document.createElement("style");
styleSheet.textContent = `
  .spin {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .hide-scrollbar {
    scrollbar-width: thin;
    scrollbar-color: #dadce0 transparent;
  }
  .hide-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .hide-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .hide-scrollbar::-webkit-scrollbar-thumb {
    background-color: #dadce0;
    border-radius: 20px;
  }
`;
document.head.appendChild(styleSheet);
