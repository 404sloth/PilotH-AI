import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  AlertTriangle,
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

type TraceStep = {
  id: string;
  label: string;
  status: "pending" | "current" | "complete" | "error";
  icon?: any;
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
  data?: Record<string, unknown>;
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
  { id: "dashboard", icon: LayoutDashboard, label: "Pulse" },
  { id: "knowledge", icon: Database, label: "Assets" },
  { id: "research", icon: Globe, label: "Market" },
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

const INITIAL_SUGGESTIONS = [
  "Check SLA compliance for V-001.",
  "Compare top cloud vendors by performance.",
  "AWS contract renewal status?",
  "Find Kubernetes vendors in Europe.",
  "Summarize yesterday's review.",
];

const AGENT_COLORS: Record<string, string> = {
  vendor_management: "#1a73e8",
  meetings_communication: "#e37400",
  knowledge_base: "#1e8e3e",
};

const AGENT_OPTIONS = [
  { id: "vendor_management", label: "Vendor Management", description: "Contracts, SLA, and scoring" },
  { id: "meetings_communication", label: "Communication", description: "Meetings and transcripts" },
  { id: "knowledge_base", label: "Knowledge Base", description: "Search docs and notes" },
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
  const cleaned = stripAgentLabel(lastMessage).replace(/\*\*/g, "").replace(/#/g, "").trim();
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
  return window.SpeechRecognition ?? (window as any).webkitSpeechRecognition;
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
          margin: "12px 0",
          paddingLeft: 24,
          color: isUser ? "#fff" : "#3c4043",
          lineHeight: 1.7,
        }}
      >
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`} style={{ marginBottom: 6 }}>
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
          margin: "14px 0",
          borderRadius: 12,
          padding: "14px 16px",
          overflowX: "auto",
          background: isUser ? "rgba(255,255,255,0.12)" : "#f1f3f4",
          color: isUser ? "#fff" : "#202124",
          fontSize: 12,
          lineHeight: 1.5,
          fontFamily: "'Fira Code', 'Courier New', monospace",
        }}
      >
        <code>{codeLines.join("\n")}</code>
      </pre>,
    );
    codeLines = [];
  };

  const flushTable = () => {
    if (!tableLines.length) return;
    // Parse table rows, handling escaped pipes and trimming
    const rows = tableLines.map((line) =>
      line
        .split(/(?<!\\)\|/)
        .map((cell) => cell.trim().replace(/\\\|/g, "|"))
        .filter(Boolean),
    );
    // Remove separator row (e.g., |---|---|)
    const bodyRows = rows.filter(
      (row, idx) => !(idx === 1 && row.every((cell) => /^:?-{3,}:?$/.test(cell))),
    );
    if (!bodyRows.length) {
      tableLines = [];
      return;
    }
    const header = bodyRows[0];
    const rest = bodyRows.slice(1);
    blocks.push(
      <div
        key={`table-wrap-${blocks.length}`}
        style={{
          overflowX: "auto",
          margin: "20px 0",
          borderRadius: 16,
          boxShadow: isUser ? "0 4px 20px rgba(0,0,0,0.15)" : "0 4px 16px rgba(0,0,0,0.04)",
          border: `1px solid ${isUser ? "rgba(255,255,255,0.15)" : "#f1f3f4"}`,
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "separate",
            borderSpacing: 0,
            background: isUser ? "rgba(255,255,255,0.06)" : "#ffffff",
            fontSize: 13,
          }}
        >
          <thead>
            <tr style={{ background: isUser ? "rgba(255,255,255,0.08)" : "rgba(0, 0, 0, 0.03)" }}>
              {header.map((cell, index) => (
                <th
                  key={`head-${index}`}
                  style={{
                    textAlign: "left",
                    padding: "16px",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    fontSize: 9,
                    color: isUser ? "rgba(255,255,255,0.8)" : "#5f6368",
                    borderBottom: `1px solid ${isUser ? "rgba(255,255,255,0.1)" : "rgba(0, 0, 0, 0.05)"}`,
                  }}
                >
                  <InlineFormat text={cell} isUser={isUser} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rest.map((row, rowIndex) => (
              <tr
                key={`row-${rowIndex}`}
                style={{
                  background: rowIndex % 2 === 0 ? "transparent" : (isUser ? "rgba(255,255,255,0.02)" : "rgba(0, 0, 0, 0.01)"),
                }}
              >
                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    style={{
                      padding: "12px 16px",
                      lineHeight: 1.6,
                      color: isUser ? "#fff" : "#3c4043",
                      borderBottom: rowIndex < rest.length - 1 ? `1px solid ${isUser ? "rgba(255,255,255,0.04)" : "rgba(0, 0, 0, 0.03)"}` : "none",
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
    const trimmed = line.trim();

    // Code block start/end
    if (trimmed.startsWith("```")) {
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

    // Table detection (must start with | after trim)
    if (trimmed.startsWith("|") && trimmed.includes("|")) {
      flushList();
      tableLines.push(line);
      continue;
    }
    flushTable();

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(trimmed)) {
      flushList();
      blocks.push(
        <hr
          key={`hr-${index}`}
          style={{
            margin: "16px 0",
            border: "none",
            borderTop: `1px solid ${isUser ? "rgba(255,255,255,0.2)" : "#e0e0e0"}`,
          }}
        />,
      );
      continue;
    }

    // Blockquote
    if (trimmed.startsWith(">")) {
      flushList();
      const quoteContent = trimmed.slice(1).trim();
      blocks.push(
        <blockquote
          key={`quote-${index}`}
          style={{
            margin: "8px 0",
            paddingLeft: 16,
            borderLeft: `3px solid ${isUser ? "rgba(255,255,255,0.4)" : "#1a73e8"}`,
            fontStyle: "italic",
            color: isUser ? "#fff" : "#5f6368",
          }}
        >
          <InlineFormat text={quoteContent} isUser={isUser} />
        </blockquote>,
      );
      continue;
    }

    // Lists
    const unorderedMatch = trimmed.match(/^[-*]\s+(.+)/);
    const orderedMatch = trimmed.match(/^\d+[.)]\s+(.+)/);
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

    // Headings
    if (trimmed.startsWith("# ")) {
      blocks.push(
        <h2
          key={`h1-${index}`}
          style={{
            margin: "24px 0 12px",
            fontSize: 22,
            fontWeight: 800,
            letterSpacing: "-0.03em",
            color: isUser ? "#fff" : "#1a73e8",
            borderBottom: isUser ? "none" : "1px solid #f1f3f4",
            paddingBottom: 8,
          }}
        >
          <InlineFormat text={trimmed.slice(2)} isUser={isUser} />
        </h2>,
      );
      continue;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push(
        <h3
          key={`h2-${index}`}
          style={{
            margin: "20px 0 10px",
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: isUser ? "#fff" : "#3c4043",
          }}
        >
          <InlineFormat text={trimmed.slice(3)} isUser={isUser} />
        </h3>,
      );
      continue;
    }
    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h4
          key={`h3-${index}`}
          style={{
            margin: "16px 0 8px",
            fontSize: 15,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            color: isUser ? "#fff" : "#5f6368",
          }}
        >
          <InlineFormat text={trimmed.slice(4)} isUser={isUser} />
        </h4>,
      );
      continue;
    }

    // Empty line
    if (!trimmed) {
      blocks.push(<div key={`spacer-${index}`} style={{ height: 12 }} />);
      continue;
    }

    // Paragraph
    blocks.push(
      <p key={`p-${index}`} style={{ margin: "6px 0", lineHeight: 1.7 }}>
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
  // Pattern: **bold** | *italic* | `code` | "quoted text"
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`|"([^"]+)")/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null = regex.exec(text);

  while (match) {
    if (match.index > lastIndex) {
      parts.push(<span key={`txt-${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>);
    }
    if (match[2] !== undefined) {
      // **bold**
      parts.push(
        <strong key={`b-${match.index}`} style={{ fontWeight: 700 }}>
          {match[2]}
        </strong>,
      );
    } else if (match[3] !== undefined) {
      // *italic*
      parts.push(
        <em key={`i-${match.index}`} style={{ fontStyle: "italic" }}>
          {match[3]}
        </em>,
      );
    } else if (match[4] !== undefined) {
      // `code`
      parts.push(
        <code
          key={`c-${match.index}`}
          style={{
            borderRadius: 6,
            padding: "2px 6px",
            background: isUser ? "rgba(255,255,255,0.15)" : "rgba(26, 115, 232, 0.05)",
            color: isUser ? "#fff" : "#1a73e8",
            border: `1px solid ${isUser ? "rgba(255,255,255,0.1)" : "rgba(26, 115, 232, 0.1)"}`,
            fontFamily: "'Fira Code', monospace",
            fontSize: "0.85em",
            fontWeight: 500,
          }}
        >
          {match[4]}
        </code>,
      );
    } else if (match[5] !== undefined) {
      // "quoted"
      parts.push(
        <span
          key={`q-${match.index}`}
          style={{
            color: isUser ? "#fff" : "#e27100",
            background: isUser ? "rgba(255,255,255,0.08)" : "rgba(226, 113, 0, 0.04)",
            padding: "0 4px",
            borderRadius: 4,
            fontWeight: 500,
            border: `1px solid ${isUser ? "rgba(255,255,255,0.05)" : "rgba(226, 113, 0, 0.08)"}`,
          }}
        >
          “{match[5]}”
        </span>,
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
      initial={{ opacity: 0, y: -20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.95 }}
      style={{
        position: "fixed",
        top: 24,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 20px",
        borderRadius: 40,
        background: type === "success" ? "#1e8e3e" : "#d93025",
        color: "#fff",
        boxShadow: "0 8px 32px rgba(0,0,0,0.15)",
        backdropFilter: "blur(12px)",
      }}
    >
      {type === "success" ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      <span style={{ fontSize: 13, fontWeight: 600 }}>{message}</span>
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
  const [routingOpen, setRoutingOpen] = useState(true);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [selectedAgentHint, setSelectedAgentHint] = useState<string | null>(null);
  const [dynamicSuggestions, setDynamicSuggestions] = useState<string[]>(INITIAL_SUGGESTIONS);
  const [tracingExtended, setTracingExtended] = useState(false);

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

      if (latestAssistantWithRouting?.metadata) {
        setLastRouting(latestAssistantWithRouting.metadata as RoutingMetadata);
        updateSuggestions(latestAssistantWithRouting.metadata as RoutingMetadata);
      }

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

    const combinedMetadata = {
      ...(parsed.metadata ?? {}),
      data: parsed.data ?? parsed.metadata?.data
    } as RoutingMetadata;

    if (parsed.metadata || parsed.data) {
      setLastRouting(combinedMetadata);

      const metaSuggestions = (parsed.metadata as any)?.suggestions as string[] | undefined;
      if (metaSuggestions && metaSuggestions.length > 0) {
        setDynamicSuggestions(metaSuggestions);
      } else {
        updateSuggestions(combinedMetadata);
      }
    }

    appendMessage({
      sender: "agent",
      text: reply,
      agent: prettifyAgent(parsed.agent),
      ts: new Date().toISOString(),
      metadata: combinedMetadata,
    });
    refreshSessionFromMessage(threadId, reply);
  }

  function updateSuggestions(metadata: RoutingMetadata) {
    const agent = metadata.agent;
    if (agent === "vendor_management") {
      setDynamicSuggestions([
        "Show scorecard for this vendor.",
        "Check SLA historical trends.",
        "Compare alternative vendors.",
        "List all cloud contracts."
      ]);
    } else if (agent === "meetings_communication") {
      setDynamicSuggestions([
        "Draft a follow-up email.",
        "Schedule review next week.",
        "Who was in the last meeting?",
        "Summarize action items."
      ]);
    } else {
      setDynamicSuggestions(INITIAL_SUGGESTIONS);
    }
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
          result: { response: string; metadata: RoutingMetadata; data?: any };
          conversation_id: string;
        }>(`${API_URL}/agents/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            conversation_id: activeSession,
            agent_hint: selectedAgentHint ?? "",
          }),
        });
        handleSocketMessage(
          JSON.stringify({
            status: "SUCCESS",
            message: result.result.response,
            thread_id: result.conversation_id,
            metadata: result.result.metadata,
            data: result.result.data,
            agent: result.result.metadata.agent,
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
      setToast({ message: "Voice not supported.", type: "error" });
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
      setDynamicSuggestions(INITIAL_SUGGESTIONS);
    } catch {
      setToast({ message: "Failed to start new Chat.", type: "error" });
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
      setToast({ message: "Failed to terminate operation log.", type: "error" });
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
          metadata: { source_description: kbSource || "Manual ingestion" },
        }),
      });
      setToast({ message: "Knowledge ingested.", type: "success" });
      setKbText("");
      setKbSource("");
    } catch {
      setToast({ message: "Failed to ingest knowledge.", type: "error" });
    } finally {
      setKbLoading(false);
    }
  }

  const mainPanel = useMemo(() => {
    if (activeTab === "dashboard") return renderDashboard(alerts, health, setActiveTab, handleSend, dynamicSuggestions);
    if (activeTab === "knowledge") {
      return renderKnowledge(kbText, kbSource, kbLoading, setKbText, setKbSource, handleKbSubmit);
    }
    if (activeTab === "research") return renderResearch(handleSend, setActiveTab);
    return null;
  }, [activeTab, alerts, health, kbText, kbSource, kbLoading, dynamicSuggestions]);

  return (
    <div style={appShellStyle}>
      <AnimatePresence>
        {toast ? (
          <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
        ) : null}
      </AnimatePresence>

      <aside
        style={{
          ...sidebarStyle,
          ...(isCollapsed ? { width: 80, padding: "24px 12px 16px" } : {})
        }}
      >
        <div style={{ ...sidebarHeaderStyle, padding: isCollapsed ? "0 0 24px" : "0 8px 24px", justifyContent: isCollapsed ? "center" : "flex-start" }}>
          <div style={{ ...logoBadgeStyle, width: isCollapsed ? 40 : 44, height: isCollapsed ? 40 : 44 }}>
            <Sparkles size={isCollapsed ? 18 : 20} color="#1a73e8" />
          </div>
          {!isCollapsed && (
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "#202124", letterSpacing: "-0.02em" }}>
                Human CoPilot
              </div>
              <div style={{ fontSize: 11, fontWeight: 500, color: "#5f6368", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                AI Executive Assistant
              </div>
            </div>
          )}
        </div>

        <button
          style={{ ...primaryPillButton, padding: isCollapsed ? "12px" : "14px 20px", justifyContent: isCollapsed ? "center" : "flex-start" }}
          onClick={() => void handleNewChat()}
        >
          <PlusCircle size={18} />
          {!isCollapsed && "New Chat"}
        </button>

        <button
          style={{
            position: "absolute",
            top: 14,
            right: isCollapsed ? -12 : 8,
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: "#fff",
            border: "1px solid #f1f3f4",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            boxShadow: "0 2px 4px rgba(0,0,0,0.05)",
            zIndex: 100,
          }}
          onClick={() => setIsCollapsed(!isCollapsed)}
        >
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown style={{ transform: "rotate(90deg)" }} size={14} />}
        </button>

        <nav style={navContainerStyle}>
          {NAV.map((item) => (
            <button
              key={item.id}
              style={{
                ...navButtonStyle,
                ...(activeTab === item.id ? activeNavButtonStyle : {}),
                justifyContent: isCollapsed ? "center" : "flex-start",
                padding: isCollapsed ? "10px 0" : "10px 16px",
              }}
              onClick={() => setActiveTab(item.id)}
              title={isCollapsed ? item.label : undefined}
            >
              <item.icon size={20} />
              {!isCollapsed && <span>{item.label}</span>}
              {activeTab === item.id && !isCollapsed ? (
                <motion.div layoutId="nav-active" style={activeNavIndicatorStyle} />
              ) : null}
            </button>
          ))}
        </nav>

        <div style={sessionsContainerStyle} className="hide-scrollbar">
          {!isCollapsed && <div style={sectionLabelStyle}>Chat History</div>}
          {sessions.map((session) => (
            <div
              key={session.id}
              style={{
                ...sessionCardStyle,
                ...(session.id === activeSession ? activeSessionCardStyle : {}),
                padding: isCollapsed ? "2px 0" : "2px 8px",
                justifyContent: isCollapsed ? "center" : "flex-start",
              }}
            >
              <button
                style={sessionButtonStyle}
                onClick={() => {
                  setActiveSession(session.id);
                  setActiveTab("conversations");
                }}
                disabled={isCollapsed && session.id === activeSession}
                title={session.title}
              >
                <div style={sessionIconStyle(session.id === activeSession)}>
                  <MessageCircle size={14} />
                </div>
                {!isCollapsed && (
                  <div style={{ minWidth: 0, flex: 1, textAlign: "left" }}>
                    <div style={sessionTitleStyle}>{session.title}</div>
                    <div style={sessionTimestampStyle}>
                      {new Date(session.updatedAt).toLocaleDateString([], { month: "short", day: "numeric" })}
                    </div>
                  </div>
                )}
              </button>
              {!isCollapsed && (
                <button style={trashButtonStyle} onClick={() => void handleDeleteChat(session.id)}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>

        <div style={sidebarFooterStyle}>
          <button style={{ ...statusToggleStyle, justifyContent: isCollapsed ? "center" : "flex-start", padding: isCollapsed ? "14px 0" : "14px 16px" }} onClick={() => setStatusOpen((open) => !open)}>
            <div style={statusIndicatorWrapStyle(connected)}>
              <div style={statusDotStyle(connected)} />
            </div>
            {!isCollapsed && "System Info"}
            {!isCollapsed && (statusOpen ? <ChevronDown size={14} style={{ marginLeft: "auto" }} /> : <ChevronRight size={14} style={{ marginLeft: "auto" }} />)}
          </button>
          <AnimatePresence>
            {statusOpen && !isCollapsed ? (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                style={{ overflow: "hidden" }}
              >
                <div style={statusCardStyle}>
                  <StatusLine label="Endpoint" value={connected ? "Secure Tunnel" : "Disconnected"} />
                  <StatusLine label="Engine DB" value={health?.database ?? "Operational"} />
                  <StatusLine label="Pilot v" value={health?.version ?? "1.3.3"} />
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </aside>

      <main style={mainStyle}>
        <header style={headerStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <h1 style={pageTitleStyle}>
              {NAV.find((item) => item.id === activeTab)?.label ?? activeTab}
            </h1>
            {isThinking ? (
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                style={thinkingBadgeStyle}
              >
                <Loader2 size={14} className="spin" />
                Thinking...
              </motion.div>
            ) : null}
          </div>
          <div style={connectionBadgeStyle(connected)}>
            {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
            {connected ? "Active" : "Offline"}
          </div>
        </header>

        {backendDown ? (
          <div style={backendWarningStyle}>
            <AlertTriangle size={18} />
            Recalibrating core. System functions may be limited.
          </div>
        ) : null}

        <div style={contentLayout}>
          {activeTab === "conversations" ? (
            <div style={chatLayoutStyle}>
              <section style={chatColumnStyle}>
                <div style={messagesPaneStyle} className="hide-scrollbar">
                  {messages.length ? (
                    messages.map((message) => <MessageRow key={message.id} msg={message} />)
                  ) : (
                    <EmptyState suggestions={dynamicSuggestions} onPickSuggestion={handleSend} />
                  )}
                  <div ref={endRef} />
                </div>

                <div style={composerOuterWrapStyle}>
                  {messages.length > 0 && (
                    <div style={contextualSuggestionsWrap} className="hide-scrollbar">
                      {dynamicSuggestions.map((suggestion, i) => (
                        <motion.button
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.05 }}
                          key={suggestion}
                          style={inlineSuggestionButtonStyle}
                          onClick={() => void handleSend(suggestion)}
                        >
                          {suggestion}
                        </motion.button>
                      ))}
                    </div>
                  )}

                  {selectedAgentHint ? (
                    <div style={selectedAgentBarStyle}>
                      <Sparkles size={12} color={AGENT_COLORS[selectedAgentHint]} />
                      <span style={selectedAgentLabelStyle}>Routing:</span>
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
                        <PlusCircle size={20} />
                      </button>
                      <AnimatePresence>
                        {agentPickerOpen ? (
                          <motion.div
                            initial={{ opacity: 0, y: 12, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: 12, scale: 0.95 }}
                            style={agentPickerMenuStyle}
                          >
                            <div style={pickerHeaderStyle}>Specialized Agents</div>
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
                                <div style={pickerItemTitleWrap}>
                                  <div style={pickerDot(AGENT_COLORS[option.id])} />
                                  <span style={agentPickerItemTitleStyle}>{option.label}</span>
                                </div>
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
                      placeholder="Ask anything..."
                      style={composerInputStyle}
                    />
                    <div style={composerActionWrap}>
                      <button type="button" style={iconCircleButton(isListening)} onClick={() => void handleVoice()}>
                        {isListening ? <Mic size={20} color="#fff" /> : <MicOff size={20} color="#5f6368" />}
                      </button>
                      <button type="submit" style={sendButtonStyle} disabled={!draft.trim()}>
                        <Send size={18} />
                      </button>
                    </div>
                  </form>
                </div>
              </section>

              <aside style={detailsPanelStyle} className="hide-scrollbar">
                <div style={detailsCardStyle}>
                  <div style={detailsHeaderWithToggle}>
                    <div style={detailsTitleStyle}>Trace</div>
                    <div style={traceIndicatorWrap}>
                      <div style={traceDot} className="pulse" />
                      Reasoning
                    </div>
                  </div>

                  <AnimatePresence mode="wait">
                    {lastRouting ? (
                      <motion.div
                        key="trace-content"
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 8 }}
                      >
                        <div style={tracePathOuterStyle}>
                          <TracePathStep label="Analyze Intent" status="complete" icon={Sparkles} />
                          <TracePathStep
                            label={prettifyAgent(lastRouting.agent) ?? "Intelligent Routing"}
                            status="complete"
                            icon={Bot}
                          />
                          <TracePathStep
                            label={lastRouting.action ?? "Executing Strategy"}
                            status="complete"
                            icon={Target}
                          />
                          <TracePathStep label="Final Briefing" status="current" icon={CheckCircle2} />
                        </div>

                        {lastRouting.intent_reasoning && (
                          <div style={{ marginTop: 20 }}>
                            <div
                              onClick={() => setTracingExtended(!tracingExtended)}
                              style={traceToggleStyle}
                            >
                              <span>{tracingExtended ? "Collapse Reasoning" : "Deep-Dive Insights"}</span>
                              <ChevronDown
                                size={14}
                                style={{
                                  transform: tracingExtended ? "rotate(180deg)" : "none",
                                  transition: "transform 0.2s",
                                }}
                              />
                            </div>
                            <AnimatePresence>
                              {tracingExtended && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  style={{ overflow: "hidden" }}
                                >
                                  <div style={reasoningBoxStyle}>
                                    <div style={reasoningLabelStyle}>Critical Path Analysis</div>
                                    <div style={{ lineHeight: 1.6, fontSize: 12.5 }}>
                                      {lastRouting.intent_reasoning}
                                    </div>
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        )}

                        <div style={{ marginTop: 24 }}>
                          <div style={detailsLabelStyle}>Tactical Capabilities</div>
                          <div style={toolsListStyle}>
                            {Object.keys(lastRouting.tool_descriptions ?? {}).map((tool) => (
                              <div key={tool} style={toolChipStyle}>
                                <div style={toolDotStyle} />
                                {tool}
                              </div>
                            ))}
                          </div>
                        </div>
                      </motion.div>
                    ) : (
                      <motion.div
                        key="trace-empty"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        style={emptyRoutingStyle}
                      >
                        Engage the core to see real-time routing logic here.
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                <div style={helpCardStyle}>
                  <div style={helpIconWrap}><Sparkles size={16} color="#1a73e8" /></div>
                  <div>
                    <div style={helpTitle}>Pro Tip</div>
                    <div style={helpText}>Force routing using the [+] menu for precise cross-domain logic.</div>
                  </div>
                </div>
              </aside>
            </div>
          ) : (
            <div style={fullPanePanel}>{mainPanel}</div>
          )}
        </div>

        <AnimatePresence>
          {pendingApproval ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={modalBackdropStyle}
            >
              <motion.div
                initial={{ scale: 0.94, y: 20 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.94, y: 20 }}
                style={modalCardStyle}
              >
                <div style={modalHeaderStyle}>
                  <div style={warningIconWrapStyle}>
                    <AlertTriangle size={20} color="#f9ab00" />
                  </div>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>Approval Gateway</div>
                    <div style={{ fontSize: 14, color: "#5f6368" }}>
                      Human intervention required for this high-impact action.
                    </div>
                  </div>
                </div>
                <div style={modalPromptWrapStyle}>
                  <pre style={modalPromptStyle}>{pendingApproval.prompt}</pre>
                </div>
                <div style={modalActionsStyle}>
                  <button
                    style={secondaryActionButton}
                    onClick={() => {
                      sendSocket({ type: "deny", task_id: pendingApproval.taskId });
                      setPendingApproval(null);
                    }}
                  >
                    <XCircle size={18} />
                    Deny
                  </button>
                  <button
                    style={primaryActionButton}
                    onClick={() => {
                      sendSocket({ type: "approve", task_id: pendingApproval.taskId });
                      setPendingApproval(null);
                    }}
                  >
                    <CheckCircle2 size={18} />
                    Approve
                  </button>
                </div>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>
    </div>
  );
}

function EmptyState({ suggestions, onPickSuggestion }: { suggestions: string[], onPickSuggestion: (text: string) => void }) {
  return (
    <div style={emptyStateWrapStyle}>
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        style={emptyLogoWrap}
      >
        <Sparkles size={42} color="#1a73e8" />
      </motion.div>
      <div style={emptyStateTitleStyle}>Human CoPilot</div>
      <div style={emptyStateSubtitleStyle}>It orchestrates complex cross-domain tasks using specialized agents.</div>
      <div style={suggestionsContainerStyle}>
        {suggestions.map((suggestion, i) => (
          <motion.button
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            key={suggestion}
            style={suggestionButtonStyle}
            onClick={() => onPickSuggestion(suggestion)}
          >
            {suggestion}
          </motion.button>
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
  suggestions: string[]
) {
  return (
    <div style={contentWrapStyle}>
      <div style={dashboardGridStyle}>
        <div style={{ ...contentCardStyle, gridColumn: "span 2" }}>
          <div style={cardHeaderStyle}>
            <span style={cardHeaderTitleStyle}>
              <AlertTriangle size={18} color="#d93025" />
              Strategic Risk Findings
            </span>
            <span style={alertCountStyle}>{alerts.length} Active</span>
          </div>
          <div style={alertsContainerStyle}>
            {alerts.length ? (
              alerts.map((alert) => (
                <div key={alert.id} style={alertCardStyle(alert.severity)}>
                  <div style={alertTitleStyle}>{alert.title}</div>
                  <div style={alertDescriptionStyle}>{alert.description}</div>
                  <div style={alertFooterStyle}>
                    <span style={alertSourceStyle}>{alert.source}</span>
                    <button style={alertActionButton}>Analyze Logic</button>
                  </div>
                </div>
              ))
            ) : (
              <div style={noAlertsStyle}>No critical alerts detected in the current landscape.</div>
            )}
          </div>
        </div>

        <div style={contentCardStyle}>
          <div style={cardHeaderStyle}>Operational Node</div>
          <div style={systemOverviewGridStyle}>
            <div style={statusGroup}>
              <div style={statusLineLabelStyle}>Core Engine</div>
              <div style={statusPill(true)}>Healthy</div>
            </div>
            <StatusLine label="Endpoint" value={health?.status ?? "Verified"} />
            <StatusLine label="Core DB" value={health?.database ?? "Operational"} />
            <StatusLine label="Pilot Latency" value="12ms" />
          </div>
        </div>

        <div style={{ ...contentCardStyle, gridColumn: "span 3" }}>
          <div style={cardHeaderStyle}>Inquiries</div>
          <div style={quickActionsContainerStyle}>
            {suggestions.map((suggestion) => (
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
            <Database size={20} color="#1a73e8" />
            Knowledge Ingestion
          </span>
        </div>
        <p style={kbIntroText}>Augment core intelligence with unstructured context payloads.</p>

        <label style={fieldLabelStyle}>Payload</label>
        <textarea
          value={kbText}
          onChange={(event) => setKbText(event.target.value)}
          rows={10}
          style={textareaStyle}
          placeholder="Paste briefs or documentation here..."
        />
        <label style={fieldLabelStyle}>Attribution</label>
        <input
          value={kbSource}
          onChange={(event) => setKbSource(event.target.value)}
          style={textInputStyle}
          placeholder="e.g., Q3 Compliance Report"
        />
        <div style={knowledgeFooterStyle}>
          <div style={wordCountStyle}>
            {kbText.trim() ? `${kbText.trim().split(/\s+/).length} words parsed` : "No payload"}
          </div>
          <button style={primaryActionButton} onClick={() => void handleKbSubmit()} disabled={kbLoading}>
            {kbLoading ? <Loader2 size={18} className="spin" /> : <PlusCircle size={18} />}
            {kbLoading ? "Indexing..." : "Submit Payload"}
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
                <category.icon size={20} color={category.color} />
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
                  <ChevronRight size={14} color="#dadce0" />
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
  const agentKey = (msg.metadata?.agent as string | undefined) ?? msg.agent?.replace(/\s+/g, "_").toLowerCase();
  const agentColor = AGENT_COLORS[agentKey ?? ""] ?? "#1a73e8";

  const isGenericMessage = msg.text.includes("Task completed successfully") || msg.text.length < 5;
  const detailedData = msg.metadata?.data as Record<string, any> | undefined;

  if (isSystem) {
    return (
      <div style={{ display: "flex", justifyContent: "center", margin: "8px 0" }}>
        <div style={systemMessageStyle}>{msg.text}</div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      style={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 12,
        margin: "6px 0",
      }}
    >
      <div style={messageIconWrap(isUser, agentColor)}>
        {isUser ? <User size={16} color="#fff" /> : <Bot size={16} color={agentColor} />}
      </div>

      <div style={{ display: "grid", gap: 4, maxWidth: "75%", minWidth: 0 }}>
        <div style={messageSenderStyle(isUser, agentColor)}>
          {isUser ? "authorized operator" : (msg.agent ?? "intel engine")}
        </div>

        <div style={messageBubbleStyle(isUser)}>
          <RichText text={stripAgentLabel(msg.text)} isUser={isUser} />

          {isGenericMessage && detailedData && Object.keys(detailedData).length > 0 && (
            <div style={dataPreviewStyle}>
              <div style={dataHeader}>Results Payload</div>
              <pre style={dataCodeStyle}>{JSON.stringify(detailedData, null, 2)}</pre>
            </div>
          )}

          {!isUser && msg.metadata && ((msg.metadata as any).agent_description || (msg.metadata as any).action_description) && (
            <div style={inlineRoutingStyle}>
              <div style={inlineRoutingHeader}>
                <Target size={10} /> Intel Route
              </div>
              <div style={inlineRoutingText}>
                {String((msg.metadata as any).agent_description ?? "")} → {String((msg.metadata as any).action_description ?? "")}
              </div>
            </div>
          )}
        </div>

        <div style={messageMetaStyle(isUser)}>
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

function DetailRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={detailRowStyle}>
      <div style={detailsLabelStyle}>{label}</div>
      <div style={detailValueStyle(highlight)}>{value}</div>
    </div>
  );
}

function TracePathStep({ label, status, icon: Icon }: { label: string, status: "pending" | "current" | "complete" | "error", icon: any }) {
  const isComplete = status === "complete";
  const isCurrent = status === "current";

  return (
    <div style={tracePathStepStyle}>
      <div style={tracePathLine(isComplete)} />
      <div style={tracePathIconBox(isComplete, isCurrent)}>
        <Icon size={12} color={isComplete || isCurrent ? "#1a73e8" : "#9aa0a6"} />
      </div>
      <div style={tracePathLabel(isComplete, isCurrent)}>{label}</div>
    </div>
  );
}

// ------------------------------------------------------------
// STYLES – CONSTRAINED SCROLLING & PREMIUM LOOK
// ------------------------------------------------------------

const appShellStyle: CSSProperties = {
  display: "flex",
  height: "100vh",
  width: "100vw",
  overflow: "hidden",
  fontFamily: '"Inter", "Outfit", -apple-system, sans-serif',
  background: "#ffffff",
  color: "#202124",
};

const sidebarStyle: CSSProperties = {
  width: 280,
  background: "#ffffff",
  padding: "24px 16px 16px",
  display: "flex",
  flexDirection: "column",
  gap: 8,
  borderRight: "1px solid #f1f3f4",
  boxShadow: "4px 0 24px rgba(0,0,0,0.02)",
  zIndex: 10,
};

const sidebarHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 14,
  padding: "0 8px 24px",
};

const logoBadgeStyle: CSSProperties = {
  width: 44,
  height: 44,
  borderRadius: 16,
  background: "#e8f0fe",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 4px 12px rgba(26,115,232,0.1)",
};

const primaryPillButton: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "14px 20px",
  borderRadius: 16,
  border: "none",
  background: "#1a73e8",
  color: "#ffffff",
  fontWeight: 600,
  fontSize: 14,
  boxShadow: "0 4px 12px rgba(26,115,232,0.25)",
  transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
  cursor: "pointer",
  marginBottom: 12,
  flexShrink: 0,
};

const navContainerStyle: CSSProperties = {
  display: "grid",
  gap: 4,
  flexShrink: 0,
};

const navButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 14,
  width: "100%",
  padding: "10px 16px",
  borderRadius: 12,
  color: "#5f6368",
  fontWeight: 500,
  fontSize: 14,
  background: "transparent",
  border: "none",
  cursor: "pointer",
  position: "relative",
};

const activeNavButtonStyle: CSSProperties = {
  color: "#1a73e8",
  background: "#f0f4f8",
};

const activeNavIndicatorStyle: CSSProperties = {
  position: "absolute",
  left: 0,
  width: 4,
  height: 16,
  background: "#1a73e8",
  borderRadius: "0 4px 4px 0",
};

const sessionsContainerStyle: CSSProperties = {
  marginTop: 24,
  paddingTop: 12,
  overflowY: "auto",
  flex: 1,
  minHeight: 0,
};

const sectionLabelStyle: CSSProperties = {
  padding: "0 16px 12px",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.1em",
  color: "#9aa0a6",
  fontWeight: 800,
  borderBottom: "1px solid #f1f3f4",
  margin: "0 8px 12px",
};

const sessionCardStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 4,
  borderRadius: 12,
  padding: "2px 8px",
  marginBottom: 4,
};

const activeSessionCardStyle: CSSProperties = {
  background: "#f8f9fa",
};

const sessionButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  flex: 1,
  minWidth: 0,
  padding: "8px",
  borderRadius: 10,
  background: "transparent",
  border: "none",
  cursor: "pointer",
  textAlign: "left",
};

const sessionIconStyle = (active: boolean): CSSProperties => ({
  width: 28,
  height: 28,
  borderRadius: 8,
  background: active ? "#e8f0fe" : "#ffffff",
  border: `1px solid ${active ? "#ceead6" : "#f1f3f4"}`,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: active ? "#1a73e8" : "#dadce0",
});

const sessionTitleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#3c4043",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const sessionTimestampStyle: CSSProperties = {
  fontSize: 10,
  color: "#9aa0a6",
  marginTop: 2,
};

const trashButtonStyle: CSSProperties = {
  padding: 8,
  borderRadius: 10,
  color: "#dadce0",
  background: "transparent",
  border: "none",
  cursor: "pointer",
};

const sidebarFooterStyle: CSSProperties = {
  marginTop: "auto",
  borderTop: "1px solid #f1f3f4",
  paddingTop: 12,
  flexShrink: 0,
};

const statusToggleStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  width: "100%",
  padding: "14px 16px",
  borderRadius: 14,
  background: "transparent",
  color: "#3c4043",
  fontWeight: 600,
  fontSize: 13,
  border: "none",
  cursor: "pointer",
};

const statusIndicatorWrapStyle = (connected: boolean): CSSProperties => ({
  width: 16,
  height: 16,
  borderRadius: 99,
  background: connected ? "#e6f4ea" : "#fce8e6",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
});

const statusDotStyle = (connected: boolean): CSSProperties => ({
  width: 6,
  height: 6,
  borderRadius: 99,
  background: connected ? "#1e8e3e" : "#d93025",
});

const statusCardStyle: CSSProperties = {
  margin: "4px 8px 12px",
  padding: "16px",
  borderRadius: 18,
  background: "#f8f9fa",
  display: "grid",
  gap: 10,
};

const mainStyle: CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
  background: "#ffffff",
  height: "100vh",
  overflow: "hidden",
};

const headerStyle: CSSProperties = {
  height: 64,
  background: "#ffffff",
  padding: "0 32px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  borderBottom: "1px solid #f1f3f4",
  flexShrink: 0,
};

const pageTitleStyle: CSSProperties = {
  fontSize: 20,
  fontWeight: 700,
  color: "#202124",
  letterSpacing: "-0.01em",
};

const thinkingBadgeStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12,
  fontWeight: 600,
  color: "#1a73e8",
  background: "#e8f0fe",
  borderRadius: 40,
  padding: "6px 12px",
};

const connectionBadgeStyle = (connected: boolean): CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  borderRadius: 40,
  padding: "6px 12px",
  fontSize: 11,
  fontWeight: 600,
  color: connected ? "#1e8e3e" : "#d93025",
  background: connected ? "#e6f4ea" : "#fce8e6",
});

const contentLayout: CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const chatLayoutStyle: CSSProperties = {
  flex: 1,
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 340px",
  gap: 0,
  minHeight: 0,
  overflow: "hidden",
};

const chatColumnStyle: CSSProperties = {
  minWidth: 0,
  display: "flex",
  flexDirection: "column",
  background: "#ffffff",
  borderRight: "1px solid #f1f3f4",
  height: "100%",
  overflow: "hidden",
};

const messagesPaneStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflowY: "auto",
  padding: "24px 40px",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const composerOuterWrapStyle: CSSProperties = {
  padding: "0 40px 24px",
  background: "#ffffff",
  borderTop: "1px solid #f8f9fa",
  flexShrink: 0,
};

const contextualSuggestionsWrap: CSSProperties = {
  display: "flex",
  flexWrap: "nowrap",
  gap: 8,
  padding: "12px 0",
  background: "#ffffff",
  overflowX: "auto",
};

const inlineSuggestionButtonStyle: CSSProperties = {
  padding: "6px 12px",
  borderRadius: 40,
  background: "#f1f3f4",
  border: "none",
  fontSize: 11,
  fontWeight: 600,
  color: "#3c4043",
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const composerWrapStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "6px 10px",
  borderRadius: 20,
  background: "#ffffff",
  boxShadow: "0 8px 32px rgba(0,0,0,0.06)",
  border: "1px solid #f1f3f4",
  marginTop: 8,
};

const composerInputStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  border: "none",
  outline: "none",
  background: "transparent",
  padding: "10px 12px",
  color: "#202124",
  fontSize: 15,
};

const composerActionWrap: CSSProperties = {
  display: "flex",
  gap: 6,
};

const iconCircleButton = (active: boolean): CSSProperties => ({
  width: 40,
  height: 40,
  borderRadius: 12,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: active ? "#d93025" : "#f8f9fa",
  border: "none",
  cursor: "pointer",
});

const sendButtonStyle: CSSProperties = {
  width: 40,
  height: 40,
  borderRadius: 12,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#1a73e8",
  color: "#ffffff",
  border: "none",
  cursor: "pointer",
  boxShadow: "0 4px 12px rgba(26,115,232,0.2)",
};

const detailsPanelStyle: CSSProperties = {
  background: "#fafbfc",
  display: "flex",
  flexDirection: "column",
  padding: "24px",
  gap: 16,
  overflowY: "auto",
  height: "100%",
};

const detailsCardStyle: CSSProperties = {
  borderRadius: 20,
  background: "#ffffff",
  padding: 20,
  boxShadow: "0 4px 12px rgba(0,0,0,0.02)",
  border: "1px solid #f1f3f4",
};

const detailsHeaderWithToggle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: 16,
};

const detailsTitleStyle: CSSProperties = {
  fontSize: 15,
  fontWeight: 700,
  color: "#202124",
};

const traceIndicatorWrap: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 10,
  fontWeight: 700,
  color: "#1e8e3e",
  textTransform: "uppercase",
};

const traceDot: CSSProperties = {
  width: 6,
  height: 6,
  borderRadius: 99,
  background: "#1e8e3e",
};

const traceSectionStyle: CSSProperties = {
  marginBottom: 12,
};

const traceQueryStyle: CSSProperties = {
  fontSize: 12,
  color: "#5f6368",
  lineHeight: 1.5,
  fontStyle: "italic",
  marginTop: 4,
};

const traceGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr",
  gap: 12,
  marginBottom: 16,
};

const detailsLabelStyle: CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  fontWeight: 700,
  color: "#80868b",
  marginBottom: 4,
};

const toolCardStyle: CSSProperties = {
  borderRadius: 12,
  background: "#f8f9fa",
  padding: "10px 12px",
  border: "1px solid #f1f3f4",
  marginBottom: 8,
};

const toolTitleStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: "#3c4043",
  marginBottom: 2,
};

const toolDescStyle: CSSProperties = {
  fontSize: 10,
  color: "#5f6368",
  lineHeight: 1.4,
};

const routePillStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "10px 14px",
  borderRadius: 14,
  background: "#f8f9fa",
  border: "1px solid #f1f3f4",
  marginBottom: 16,
};

const routeStepStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12,
  fontWeight: 600,
  color: "#3c4043",
};

const routeDot = (color: string): CSSProperties => ({
  width: 6,
  height: 6,
  borderRadius: 99,
  background: color,
});

const tracePathOuterStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 0,
  padding: "4px 0",
};

const tracePathStepStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 16,
  position: "relative",
  padding: "10px 0",
};

const tracePathLine = (complete: boolean): CSSProperties => ({
  position: "absolute",
  left: 13,
  top: 30,
  bottom: -10,
  width: 2,
  background: complete ? "#e8f0fe" : "#f1f3f4",
  zIndex: 1,
});

const tracePathIconBox = (complete: boolean, current: boolean): CSSProperties => ({
  width: 28,
  height: 28,
  borderRadius: 10,
  background: current || complete ? "#e8f0fe" : "#f8f9fa",
  border: `1px solid ${current || complete ? "#d2e3fc" : "#f1f3f4"}`,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 2,
  boxShadow: current ? "0 0 0 4px rgba(26,115,232,0.1)" : "none",
});

const tracePathLabel = (complete: boolean, current: boolean): CSSProperties => ({
  fontSize: 13,
  fontWeight: current ? 700 : 500,
  color: current ? "#1a73e8" : (complete ? "#3c4043" : "#9aa0a6"),
});

const traceToggleStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "12px 14px",
  borderRadius: 12,
  background: "#f8f9fa",
  border: "1px solid #f1f3f4",
  fontSize: 11,
  fontWeight: 700,
  color: "#1a73e8",
  cursor: "pointer",
  transition: "all 0.2s",
  marginTop: 12,
};

const reasoningBoxStyle: CSSProperties = {
  marginTop: 12,
  padding: "16px",
  borderRadius: 14,
  background: "rgba(26,115,232,0.03)",
  border: "1px solid rgba(26,115,232,0.08)",
  color: "#3c4043",
  boxShadow: "0 2px 8px rgba(0,0,0,0.02)",
};

const reasoningLabelStyle: CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  fontWeight: 800,
  color: "#1a73e8",
  marginBottom: 10,
  display: "block",
};

const toolsListStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
};

const toolChipStyle: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "6px 12px",
  borderRadius: 10,
  background: "#f0f4f8",
  color: "#1a73e8",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  display: "flex",
  alignItems: "center",
  border: "1px solid #e8f0fe",
};

const toolDotStyle: CSSProperties = {
  width: 5,
  height: 5,
  borderRadius: 99,
  background: "#1a73e8",
  marginRight: 8,
};

const helpCardStyle: CSSProperties = {
  display: "flex",
  gap: 12,
  padding: "16px",
  borderRadius: 16,
  background: "#e8f0fe80",
  border: "1px solid #e8f0fe",
};

const helpIconWrap: CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: 8,
  background: "#ffffff",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
};

const helpTitle: CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: "#1a73e8",
  marginBottom: 2,
};

const helpText: CSSProperties = {
  fontSize: 11,
  color: "#5f6368",
  lineHeight: 1.4,
};

const selectedAgentBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "0 12px 4px",
};

const selectedAgentLabelStyle: CSSProperties = {
  fontSize: 10,
  color: "#9aa0a6",
  fontWeight: 700,
  textTransform: "uppercase",
};

const clearAgentHintButtonStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#dadce0",
  background: "transparent",
  border: "none",
  padding: 4,
  cursor: "pointer",
};

const agentPickerWrapStyle: CSSProperties = {
  position: "relative",
};

const agentPickerButtonStyle: CSSProperties = {
  width: 40,
  height: 40,
  borderRadius: 12,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "#f8f9fa",
  color: "#5f6368",
  border: "none",
  cursor: "pointer",
};

const agentPickerMenuStyle: CSSProperties = {
  position: "absolute",
  left: 0,
  bottom: "calc(100% + 12px)",
  width: 260,
  borderRadius: 20,
  background: "#ffffff",
  boxShadow: "0 16px 40px rgba(0,0,0,0.12)",
  border: "1px solid #f1f3f4",
  padding: 10,
  display: "grid",
  gap: 2,
  zIndex: 100,
};

const pickerHeaderStyle: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: "#9aa0a6",
  padding: "6px 10px",
  textTransform: "uppercase",
};

const pickerItemTitleWrap: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
};

const pickerDot = (color: string): CSSProperties => ({
  width: 6,
  height: 6,
  borderRadius: 99,
  background: color,
});

const agentPickerItemStyle = (active: boolean): CSSProperties => ({
  display: "grid",
  gap: 2,
  textAlign: "left",
  padding: "10px 12px",
  borderRadius: 12,
  background: active ? "#f0f4f8" : "transparent",
  color: active ? "#1a73e8" : "#3c4043",
  border: "none",
  cursor: "pointer",
});

const agentPickerItemTitleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
};

const agentPickerItemDescriptionStyle: CSSProperties = {
  fontSize: 11,
  color: "#80868b",
};

const agentHintChipStyle = (agentId: string): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  borderRadius: 99,
  padding: "2px 8px",
  background: `${AGENT_COLORS[agentId] ?? "#1a73e8"}15`,
  color: AGENT_COLORS[agentId] ?? "#1a73e8",
  fontSize: 10,
  fontWeight: 700,
});

const emptyStateWrapStyle: CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 12,
  textAlign: "center",
  padding: "40px 20px",
};

const emptyLogoWrap: CSSProperties = {
  width: 72,
  height: 72,
  borderRadius: 24,
  background: "#e8f0fe",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  marginBottom: 8,
};

const emptyStateTitleStyle: CSSProperties = {
  fontSize: 24,
  fontWeight: 800,
  color: "#202124",
  letterSpacing: "-0.02em",
};

const emptyStateSubtitleStyle: CSSProperties = {
  fontSize: 14,
  color: "#5f6368",
  maxWidth: 440,
  lineHeight: 1.5,
};

const suggestionsContainerStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 10,
  justifyContent: "center",
  marginTop: 20,
  maxWidth: 640,
};

const suggestionButtonStyle: CSSProperties = {
  borderRadius: 12,
  border: "1px solid #f1f3f4",
  padding: "10px 16px",
  background: "#ffffff",
  color: "#3c4043",
  fontWeight: 600,
  fontSize: 12,
  boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
  cursor: "pointer",
};

const systemMessageStyle: CSSProperties = {
  maxWidth: "80%",
  borderRadius: 16,
  background: "#fff9e6",
  color: "#663c00",
  fontSize: 13,
  fontWeight: 500,
  lineHeight: 1.5,
  padding: "10px 18px",
  border: "1px solid #ffe2b9",
};

const inlineRoutingStyle: CSSProperties = {
  marginTop: 12,
  paddingTop: 10,
  borderTop: "1px solid rgba(0,0,0,0.05)",
};

const inlineRoutingHeader: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 9,
  fontWeight: 800,
  color: "#9aa0a6",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginBottom: 4,
};

const inlineRoutingText: CSSProperties = {
  fontSize: 11,
  color: "#80868b",
  lineHeight: 1.4,
  fontWeight: 500,
};

const messageIconWrap = (isUser: boolean, agentColor: string): CSSProperties => ({
  width: 34,
  height: 34,
  borderRadius: 10,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: isUser ? "#1a73e8" : "#ffffff",
  boxShadow: isUser ? "0 4px 10px rgba(26,115,232,0.2)" : "0 2px 6px rgba(0,0,0,0.04)",
  border: isUser ? "none" : "1px solid #f1f3f4",
  flexShrink: 0,
});

const messageSenderStyle = (isUser: boolean, agentColor: string): CSSProperties => ({
  fontSize: 10,
  fontWeight: 800,
  color: isUser ? "#1a73e8" : agentColor,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  marginLeft: 2,
});

const messageBubbleStyle = (isUser: boolean): CSSProperties => ({
  borderRadius: isUser ? "24px 4px 24px 24px" : "4px 24px 24px 24px",
  padding: "12px 18px",
  background: isUser ? "linear-gradient(135deg, #1a73e8 0%, #1557b0 100%)" : "#ffffff",
  color: isUser ? "#ffffff" : "#202124",
  boxShadow: isUser ? "0 4px 14px rgba(26,115,232,0.18)" : "0 2px 10px rgba(0,0,0,0.03)",
  border: isUser ? "none" : "1px solid #f1f3f4",
  position: "relative",
  fontSize: 15,
  lineHeight: 1.6,
});

const messageMetaStyle = (isUser: boolean): CSSProperties => ({
  fontSize: 9,
  color: "#9aa0a6",
  display: "flex",
  alignItems: "center",
  justifyContent: isUser ? "flex-end" : "flex-start",
  gap: 6,
  marginTop: 2,
  padding: "0 2px",
});

const dataPreviewStyle: CSSProperties = {
  marginTop: 10,
  padding: 12,
  borderRadius: 12,
  background: "rgba(0,0,0,0.03)",
  border: "1px solid rgba(0,0,0,0.05)",
  overflowX: "auto"
};

const dataHeader: CSSProperties = {
  fontSize: 10,
  fontWeight: 800,
  color: "#5f6368",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: 6,
};

const dataCodeStyle: CSSProperties = {
  fontSize: 11,
  color: "#3c4043",
  fontFamily: "'Fira Code', monospace",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  margin: 0,
};

const statusLineStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 12,
  fontSize: 12,
};

const statusLineLabelStyle: CSSProperties = {
  color: "#80868b",
  fontWeight: 500,
};

const statusLineValueStyle: CSSProperties = {
  color: "#3c4043",
  fontWeight: 700,
};

const statusGroup: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: 6,
};

const statusPill = (healthy: boolean): CSSProperties => ({
  padding: "2px 8px",
  borderRadius: 99,
  background: healthy ? "#e6f4ea" : "#fce8e6",
  color: healthy ? "#1e8e3e" : "#d93025",
  fontSize: 10,
  fontWeight: 800,
  textTransform: "uppercase",
});

const detailRowStyle: CSSProperties = {
  marginBottom: 12,
};

const detailValueStyle = (highlight: boolean): CSSProperties => ({
  fontSize: 13,
  fontWeight: highlight ? 700 : 500,
  color: highlight ? "#1a73e8" : "#3c4043",
  lineHeight: 1.4,
  wordBreak: "break-word",
});

const fullPanePanel: CSSProperties = {
  flex: 1,
  height: "100%",
  overflowY: "auto",
};

const contentWrapStyle: CSSProperties = {
  padding: 32,
  height: "100%",
};

const dashboardGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  gap: 20,
};

const contentCardStyle: CSSProperties = {
  borderRadius: 24,
  background: "#ffffff",
  padding: 24,
  boxShadow: "0 4px 20px rgba(0,0,0,0.02)",
  border: "1px solid #f1f3f4",
};

const singleColumnCardStyle: CSSProperties = {
  ...contentCardStyle,
  maxWidth: 800,
  margin: "0 auto",
};

const cardHeaderStyle: CSSProperties = {
  fontSize: 16,
  fontWeight: 800,
  color: "#202124",
  marginBottom: 20,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
};

const cardHeaderTitleStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
};

const alertCountStyle: CSSProperties = {
  color: "#d93025",
  fontSize: 11,
  fontWeight: 800,
  textTransform: "uppercase",
  background: "#fce8e6",
  padding: "3px 10px",
  borderRadius: 99,
};

const alertsContainerStyle: CSSProperties = {
  display: "grid",
  gap: 12,
};

const alertCardStyle = (severity: AlertItem["severity"]): CSSProperties => ({
  borderRadius: 16,
  padding: 16,
  border: "1px solid #f1f3f4",
  borderLeft: `4px solid ${severity === "high" ? "#d93025" : severity === "medium" ? "#f9ab00" : "#1e8e3e"
    }`,
  background: "#fafbfc",
  display: "grid",
  gap: 6,
});

const alertTitleStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: "#202124",
};

const alertDescriptionStyle: CSSProperties = {
  color: "#5f6368",
  fontSize: 13,
  lineHeight: 1.5,
};

const alertFooterStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginTop: 4,
};

const alertSourceStyle: CSSProperties = {
  color: "#9aa0a6",
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
};

const alertActionButton: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: "#1a73e8",
  background: "transparent",
  border: "none",
  cursor: "pointer",
};

const noAlertsStyle: CSSProperties = {
  color: "#9aa0a6",
  fontSize: 14,
  textAlign: "center",
  padding: "32px 0",
};

const systemOverviewGridStyle: CSSProperties = {
  display: "grid",
  gap: 12,
};

const quickActionsContainerStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 10,
};

const kbIntroText: CSSProperties = {
  fontSize: 14,
  color: "#5f6368",
  marginBottom: 24,
  lineHeight: 1.5,
};

const fieldLabelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 800,
  marginBottom: 6,
  color: "#3c4043",
  textTransform: "uppercase",
};

const textareaStyle: CSSProperties = {
  width: "100%",
  borderRadius: 16,
  border: "1px solid #f1f3f4",
  background: "#f8f9fa",
  padding: 16,
  resize: "none",
  color: "#202124",
  fontSize: 14,
  lineHeight: 1.5,
  marginBottom: 20,
  outline: "none",
};

const textInputStyle: CSSProperties = {
  width: "100%",
  borderRadius: 12,
  border: "1px solid #f1f3f4",
  background: "#f8f9fa",
  padding: "12px 16px",
  color: "#202124",
  fontSize: 14,
  outline: "none",
};

const knowledgeFooterStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginTop: 24,
};

const wordCountStyle: CSSProperties = {
  fontSize: 12,
  fontWeight: 500,
  color: "#9aa0a6",
};

const researchGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
  gap: 20,
};

const researchQueriesContainerStyle: CSSProperties = {
  display: "grid",
  gap: 10,
};

const researchButtonStyle: CSSProperties = {
  textAlign: "left",
  borderRadius: 14,
  border: "1px solid #f1f3f4",
  background: "#ffffff",
  padding: "12px 16px",
  color: "#3c4043",
  fontSize: 13,
  fontWeight: 600,
  lineHeight: 1.4,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: 10,
};

const emptyRoutingStyle: CSSProperties = {
  fontSize: 13,
  color: "#9aa0a6",
  lineHeight: 1.6,
  textAlign: "center",
  padding: "32px 20px",
};

const toolsGridStyle: CSSProperties = {
  display: "grid",
  gap: 10,
};

const backendWarningStyle: CSSProperties = {
  margin: "12px 32px 0",
  borderRadius: 12,
  background: "#fff4e5",
  color: "#663c00",
  display: "flex",
  gap: 10,
  alignItems: "center",
  padding: "10px 16px",
  fontSize: 12,
  fontWeight: 600,
  border: "1px solid #ffe2b9",
  flexShrink: 0,
};

const modalBackdropStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(32, 33, 36, 0.4)",
  backdropFilter: "blur(6px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalCardStyle: CSSProperties = {
  width: "min(520px, 92vw)",
  borderRadius: 28,
  background: "#ffffff",
  padding: 28,
  boxShadow: "0 24px 48px rgba(0,0,0,0.18)",
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
  borderRadius: 14,
  background: "#fff9e6",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const modalPromptWrapStyle: CSSProperties = {
  borderRadius: 16,
  background: "#f8f9fa",
  padding: 16,
  marginBottom: 24,
  border: "1px solid #f1f3f4",
};

const modalPromptStyle: CSSProperties = {
  whiteSpace: "pre-wrap",
  fontSize: 13,
  lineHeight: 1.6,
  color: "#3c4043",
  margin: 0,
  fontFamily: "inherit",
};

const modalActionsStyle: CSSProperties = {
  display: "flex",
  gap: 12,
};

const secondaryActionButton: CSSProperties = {
  flex: 1,
  borderRadius: 14,
  border: "none",
  padding: "14px 18px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontWeight: 700,
  fontSize: 13,
  color: "#5f6368",
  background: "#f1f3f4",
  cursor: "pointer",
};

const primaryActionButton: CSSProperties = {
  flex: 1,
  borderRadius: 14,
  border: "none",
  padding: "14px 18px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontWeight: 700,
  fontSize: 13,
  color: "#ffffff",
  background: "#1a73e8",
  boxShadow: "0 4px 12px rgba(26,115,232,0.2)",
  cursor: "pointer",
};

// Global animations
const styleSheet = document.createElement("style");
styleSheet.textContent = `
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .spin {
    animation: spin 1s linear infinite;
  }
  @keyframes pulse {
    0% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.1); opacity: 0.8; }
    100% { transform: scale(1); opacity: 1; }
  }
  .pulse {
    animation: pulse 2s infinite ease-in-out;
  }
  .hide-scrollbar {
    scrollbar-width: none;
    -ms-overflow-style: none;
  }
  .hide-scrollbar::-webkit-scrollbar {
    display: none;
  }
`;
document.head.appendChild(styleSheet);
