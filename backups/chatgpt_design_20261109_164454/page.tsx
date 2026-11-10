
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import ExploreDiscover from "./explore-discover";
import PortfolioBuilder from "./portfolio-builder";
import LearnPage from "./learn";

import {
  Activity,
  ArrowDownRight,
  ArrowUp,
  ArrowUpRight,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  ChevronDown,
  Compass,
  FlaskConical,
  LayoutDashboard,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// --------------------------------------------------
// NAVIGATION
// --------------------------------------------------

const navigation = [
  { name: "Dashboard", icon: LayoutDashboard },
  { name: "Ask GREEDY", icon: MessageSquare },
  { name: "Explore & Discover", icon: Compass },
  { name: "Portfolio Builder", icon: BriefcaseBusiness },
  { name: "Greedy Lab", icon: FlaskConical },
  { name: "Learn", icon: BookOpen },
];

// --------------------------------------------------
// ILLUSTRATIVE DASHBOARD DATA
// --------------------------------------------------

const chartData = [
  { day: "Mon", value: 22100 },
  { day: "Tue", value: 22240 },
  { day: "Wed", value: 22180 },
  { day: "Thu", value: 22400 },
  { day: "Fri", value: 22350 },
  { day: "Sat", value: 22520 },
  { day: "Sun", value: 22680 },
];

const stocks = [
  {
    name: "Reliance Industries",
    symbol: "RELIANCE",
    price: "1,452.60",
    change: "+1.84%",
    positive: true,
  },
  {
    name: "HDFC Bank",
    symbol: "HDFCBANK",
    price: "1,008.25",
    change: "+0.92%",
    positive: true,
  },
  {
    name: "Infosys",
    symbol: "INFY",
    price: "1,624.80",
    change: "-0.65%",
    positive: false,
  },
  {
    name: "ICICI Bank",
    symbol: "ICICIBANK",
    price: "1,345.10",
    change: "+1.21%",
    positive: true,
  },
];

const periods = ["1W", "1M", "3M", "6M", "1Y"];

// --------------------------------------------------
// CHAT TYPES
// --------------------------------------------------

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
};

type ChatApiResponse = {
  conversation_id: number;
  user_message: string;
  assistant_message: string;
  created_at: string;
};

type ConversationHistoryResponse = {
  conversation: {
    id: number;
    title: string;
    created_at: string;
    updated_at: string;
  };
  messages: Array<{
    id: number;
    role: "user" | "assistant" | "system" | "tool";
    content: string;
    created_at: string;
  }>;
};

type ConversationListItem = {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  last_message: string | null;
  message_count: number;
};

type ConversationListResponse = {
  conversations: ConversationListItem[];
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --------------------------------------------------
// MARKDOWN RESPONSE RENDERER
// --------------------------------------------------

function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="greedy-markdown min-w-0 text-sm leading-7 text-[#e5e5e5]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mb-4 mt-7 text-2xl font-bold tracking-tight text-white first:mt-0">
              {children}
            </h1>
          ),

          h2: ({ children }) => (
            <h2 className="mb-3 mt-7 text-xl font-bold tracking-tight text-white first:mt-0">
              {children}
            </h2>
          ),

          h3: ({ children }) => (
            <h3 className="mb-2 mt-6 text-base font-bold text-white first:mt-0">
              {children}
            </h3>
          ),

          h4: ({ children }) => (
            <h4 className="mb-2 mt-4 text-sm font-bold text-white">
              {children}
            </h4>
          ),

          p: ({ children }) => (
            <p className="mb-4 leading-7 last:mb-0">
              {children}
            </p>
          ),

          strong: ({ children }) => (
            <strong className="font-bold text-white">
              {children}
            </strong>
          ),

          em: ({ children }) => (
            <em className="italic text-[#dddddd]">
              {children}
            </em>
          ),

          ul: ({ children }) => (
            <ul className="mb-4 ml-6 list-disc space-y-2 marker:text-[#aaaaaa]">
              {children}
            </ul>
          ),

          ol: ({ children }) => (
            <ol className="mb-4 ml-6 list-decimal space-y-2 marker:text-[#aaaaaa]">
              {children}
            </ol>
          ),

          li: ({ children }) => (
            <li className="pl-1 leading-7">
              {children}
            </li>
          ),

          hr: () => (
            <hr className="my-6 border-[#505050]" />
          ),

          blockquote: ({ children }) => (
            <blockquote className="my-5 border-l-2 border-[#888888] pl-4 text-[#bdbdbd]">
              {children}
            </blockquote>
          ),

          code: ({ children, className }) => {
            const isBlock = Boolean(className);

            return isBlock ? (
              <code className="block overflow-x-auto rounded-lg bg-[#171717] p-4 text-xs leading-6 text-[#dddddd]">
                {children}
              </code>
            ) : (
              <code className="rounded bg-[#414141] px-1.5 py-1 text-xs text-[#eeeeee]">
                {children}
              </code>
            );
          },

          pre: ({ children }) => (
            <pre className="my-4 overflow-x-auto rounded-xl border border-[#414141] bg-[#171717] p-4">
              {children}
            </pre>
          ),

          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#b8cfff] underline underline-offset-4 hover:text-white"
            >
              {children}
            </a>
          ),

          table: ({ children }) => (
            <div className="my-5 overflow-x-auto rounded-xl border border-[#414141]">
              <table className="w-full border-collapse text-left text-xs">
                {children}
              </table>
            </div>
          ),

          th: ({ children }) => (
            <th className="border-b border-[#505050] bg-[#353535] px-4 py-3 font-semibold text-white">
              {children}
            </th>
          ),

          td: ({ children }) => (
            <td className="border-b border-[#414141] px-4 py-3">
              {children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// --------------------------------------------------
// ASK GREEDY CHAT
// --------------------------------------------------

function AskGreedyChat({
  initialQuestion,
  initialConversationId,
  onConversationUpdated,
}: {
  initialQuestion: string;
  initialConversationId: number | null;
  onConversationUpdated: () => void;
}) {
  const [draft, setDraft] = useState(initialQuestion);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(
    initialConversationId
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(initialQuestion);
  }, [initialQuestion]);

  // Restore saved messages whenever a conversation ID is present in the URL.
  useEffect(() => {
    if (!initialConversationId) {
      setConversationId(null);
      setMessages([]);
      return;
    }

    const controller = new AbortController();

    async function restoreConversation() {
      setLoading(true);
      setError("");

      try {
        const response = await fetch(
          `${API_BASE_URL}/chat/conversations/${initialConversationId}`,
          {
            method: "GET",
            cache: "no-store",
            signal: controller.signal,
          }
        );

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail || "GREEDY could not restore this conversation."
          );
        }

        const result = data as ConversationHistoryResponse;

        if (controller.signal.aborted) return;

        setConversationId(result.conversation.id);
        setMessages(
          result.messages
            .filter(
              (message) =>
                message.role === "user" || message.role === "assistant"
            )
            .map((message) => ({
              id: message.id,
              role: message.role as "user" | "assistant",
              content: message.content,
            }))
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;

        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Conversation restoration failed."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void restoreConversation();

    return () => controller.abort();
  }, [initialConversationId]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const question = draft.trim();

    if (!question || loading) return;

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: question,
    };

    setMessages((previous) => [...previous, userMessage]);
    setDraft("");
    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: question,
          conversation_id: conversationId,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "GREEDY could not process your message."
        );
      }

      const result = data as ChatApiResponse;

      setConversationId(result.conversation_id);

      // Keep the conversation addressable after refresh or when the URL is shared.
      const conversationUrl = `/?conversation=${result.conversation_id}`;
      window.history.replaceState(null, "", conversationUrl);

      setMessages((previous) => [
        ...previous,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: result.assistant_message,
        },
      ]);
      onConversationUpdated();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again."
      );

      setDraft(question);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#000000]">
      <div className="flex flex-1 flex-col px-4 md:px-10">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">

          {/* EMPTY CHAT STATE */}

          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">

              <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#303030] text-[#e5e5e5]">
                <MessageSquare size={26} />
              </div>

              <h1 className="text-3xl font-semibold tracking-tight text-[#ececec] md:text-4xl">
                What would you like to understand?
              </h1>

              <p className="mt-4 max-w-md text-sm leading-7 text-[#a0a0a0]">
                Ask about NIFTY 50 companies, stock market concepts,
                historical performance, financial metrics and risk.
                GREEDY is here to make things simple.
              </p>

              <div className="mt-9 grid w-full gap-3 sm:grid-cols-2">
                {[
                  "Explain NIFTY 50 in simple words",
                  "How do I understand stock returns?",
                  "What is the difference between risk and volatility?",
                  "How should I analyse a company?",
                ].map((question) => (
                  <button
                    key={question}
                    onClick={() => setDraft(question)}
                    className="rounded-xl border border-[#414141] bg-[#2a2a2a] p-4 text-left text-xs leading-5 text-[#d4d4d4] transition hover:border-[#666666] hover:bg-[#353535]"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (

            /* CHAT MESSAGES */

            <div className="flex-1 space-y-7 py-8">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${
                    message.role === "user"
                      ? "justify-end"
                      : "justify-start"
                  }`}
                >
                  <div
                    className={`min-w-0 max-w-[95%] rounded-2xl px-5 py-4 md:max-w-[90%] ${
                      message.role === "user"
                        ? "whitespace-pre-wrap rounded-br-md bg-[#303030] text-sm leading-7 text-[#ececec]"
                        : "rounded-bl-md bg-[#292929] text-[#e5e5e5]"
                    }`}
                  >
                    {message.role === "assistant" ? (
                      <AssistantMarkdown content={message.content} />
                    ) : (
                      message.content
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-3 rounded-2xl bg-[#292929] px-5 py-4 text-sm text-[#a0a0a0]">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-[#aaaaaa]" />
                    GREEDY is thinking...
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-red-900 bg-[#351f1f] p-4 text-sm text-red-200">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* MESSAGE COMPOSER */}

          <div className="sticky bottom-0 mt-auto bg-[#000000] pb-6 pt-5">
            <form
              onSubmit={handleSubmit}
              className="rounded-3xl border border-[#414141] bg-[#303030] p-3 shadow-2xl transition focus-within:border-[#666666]"
            >
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();

                    if (draft.trim() && !loading) {
                      event.currentTarget.form?.requestSubmit();
                    }
                  }
                }}
                rows={2}
                placeholder="Message GREEDY..."
                disabled={loading}
                className="max-h-40 min-h-12 w-full resize-y bg-transparent px-3 py-2 text-sm leading-6 text-[#ececec] outline-none placeholder:text-[#a0a0a0] disabled:opacity-60"
              />

              <div className="flex items-center justify-between px-1 pt-2">
                <p className="text-[10px] text-[#a0a0a0]">
                  Ask anything about the Indian stock market
                </p>

                <button
                  type="submit"
                  disabled={!draft.trim() || loading}
                  aria-label="Send message"
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ececec] text-[#171717] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ArrowUp size={19} />
                </button>
              </div>
            </form>

            <p className="mt-3 text-center text-[10px] text-[#888888]">
              GREEDY STOCKS Â· Educational research only Â· Not investment advice
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------
// MAIN APPLICATION CONTENT
// --------------------------------------------------

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const questionFromUrl = searchParams.get("question") || "";
  const conversationParam = searchParams.get("conversation") || "";
  const stockFromUrl = (searchParams.get("addStock") || "").toUpperCase().trim();

  const parsedConversationId =
    /^\d+$/.test(conversationParam) &&
    Number.isSafeInteger(Number(conversationParam)) &&
    Number(conversationParam) > 0
      ? Number(conversationParam)
      : null;

  const [activeNav, setActiveNav] = useState(
    "Ask GREEDY"
  );

  const [activePeriod, setActivePeriod] = useState("1W");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const refreshConversations = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError("");

    try {
      const response = await fetch(`${API_BASE_URL}/chat/conversations`, {
        method: "GET",
        cache: "no-store",
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not load chat history.");
      }

      setConversations(
        ((data as ConversationListResponse).conversations || []).filter(
          (conversation) => Number.isSafeInteger(conversation.id)
        )
      );
    } catch (err) {
      setHistoryError(
        err instanceof Error ? err.message : "Could not load chat history."
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  function startNewChat() {
    setActiveNav("Ask GREEDY");
    setMobileMenu(false);
    router.push("/");
  }

  function openConversation(id: number) {
    setActiveNav("Ask GREEDY");
    setMobileMenu(false);
    router.push(`/?conversation=${id}`);
  }

  async function removeConversation(id: number) {
    const confirmed = window.confirm(
      "Delete this conversation permanently?"
    );

    if (!confirmed) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/chat/conversations/${id}`,
        { method: "DELETE" }
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not delete conversation.");
      }

      setConversations((previous) =>
        previous.filter((conversation) => conversation.id !== id)
      );

      if (parsedConversationId === id) {
        setActiveNav("Ask GREEDY");
        router.replace("/");
      }
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "Could not delete conversation."
      );
    }
  }

  const currentNav =
    questionFromUrl || parsedConversationId
      ? "Ask GREEDY"
      : stockFromUrl
        ? "Portfolio Builder"
        : activeNav;

  function handleNavigation(name: string) {
    setActiveNav(name);
    setMobileMenu(false);

    if (
      name !== "Ask GREEDY" &&
      (questionFromUrl || conversationParam || stockFromUrl)
    ) {
      router.replace("/");
    }
  }

  function toggleMobileMenu() {
    setMobileMenu((value) => !value);
  }

  return (
    <main className="min-h-screen bg-[#000000] text-[#ececec]">
      <div className="flex min-h-screen">

        {/* MOBILE BACKDROP */}

        {mobileMenu && (
          <button
            aria-label="Close navigation"
            onClick={() => setMobileMenu(false)}
            className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          />
        )}

        {/* SIDEBAR */}

        <aside
          className={`
            fixed inset-y-0 left-0 z-50 flex flex-col
            border-r border-[#303030] bg-[#171717]
            p-4 transition-all duration-200
            lg:static lg:translate-x-0
            ${sidebarCollapsed ? "lg:w-[76px]" : "lg:w-64"}
            ${
              mobileMenu
                ? "w-64 translate-x-0"
                : "-translate-x-full lg:translate-x-0"
            }
          `}
        >

          {/* BRAND WITH HOVER SIDEBAR TOGGLE */}

<div
  className={`group relative mb-10 flex h-10 items-center ${
    sidebarCollapsed ? "justify-center" : "gap-3"
  }`}
>
  {/* LOGO ICON */}

  <div className="relative flex h-10 w-10 shrink-0 items-center justify-center">
    <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[#eeeeee] text-[#171717] transition-opacity duration-150 group-hover:opacity-0">
      <TrendingUp size={23} strokeWidth={2.5} />
    </div>

    {/* TOGGLE APPEARS ON HOVER */}

    <button
      onClick={() => setSidebarCollapsed((value) => !value)}
      aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="absolute inset-0 hidden items-center justify-center rounded-xl text-[#aaaaaa] transition-colors duration-150 hover:bg-[#000000] hover:text-white group-hover:opacity-100 lg:flex"
    >
      {sidebarCollapsed ? (
        <PanelLeftOpen size={21} />
      ) : (
        <PanelLeftClose size={21} />
      )}
    </button>
  </div>

  {/* BRAND TEXT */}

  {!sidebarCollapsed && (
    <div>
      <h1 className="text-lg font-black tracking-wider text-[#eeeeee]">
        GREEDY<span className="text-[#a0a0a0]">.</span>
      </h1>

      <p className="text-[10px] tracking-[0.25em] text-[#888888]">
        STOCKS
      </p>
    </div>
  )}
</div>

          {/* WORKSPACE LABEL */}

          <p
            className={`mb-3 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-[#777777] ${
              sidebarCollapsed ? "lg:hidden" : ""
            }`}
          >
            Workspace
          </p>

          {/* NAVIGATION */}

          <nav className="flex flex-col gap-1">
            {navigation.map((item) => {
              const Icon = item.icon;
              const active = currentNav === item.name;

              return (
                <button
                  key={item.name}
                  onClick={() => handleNavigation(item.name)}
                  title={sidebarCollapsed ? item.name : undefined}
                  aria-label={item.name}
                  className={`
                    flex items-center rounded-xl px-3 py-3 text-left
                    text-sm transition
                    ${sidebarCollapsed ? "lg:justify-center" : "gap-3"}
                    ${
                      active
                        ? "bg-[#303030] font-semibold text-[#ffffff]"
                        : "text-[#a0a0a0] hover:bg-[#2a2a2a] hover:text-[#eeeeee]"
                    }
                  `}
                >
                  <Icon size={19} className="shrink-0" />

                  <span className={sidebarCollapsed ? "lg:hidden" : ""}>
                    {item.name}
                  </span>
                </button>
              );
            })}
          </nav>

          {/* SAVED CONVERSATION HISTORY */}

          <div className={`mt-7 flex min-h-0 flex-1 flex-col ${sidebarCollapsed ? "lg:hidden" : ""}`}>
            <div className="mb-3 flex items-center justify-between px-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#777777]">
                Your chats
              </p>
              <button
                onClick={startNewChat}
                title="Start a new chat"
                aria-label="Start a new chat"
                className="rounded-lg p-1.5 text-[#aaaaaa] transition hover:bg-[#000000] hover:text-white"
              >
                <MessageSquare size={15} />
              </button>
            </div>

            <button
              onClick={startNewChat}
              className="mb-2 flex items-center gap-2 rounded-xl border border-[#414141] px-3 py-2.5 text-left text-xs font-semibold text-[#dddddd] transition hover:bg-[#2a2a2a] hover:text-white"
            >
              <span className="text-base leading-none">+</span>
              New Chat
            </button>

            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
              {historyLoading && conversations.length === 0 ? (
                <p className="px-3 py-2 text-xs text-[#888888]">Loading chats...</p>
              ) : historyError ? (
                <p className="px-3 py-2 text-xs text-red-300">{historyError}</p>
              ) : conversations.length === 0 ? (
                <p className="px-3 py-2 text-xs leading-5 text-[#777777]">
                  Your saved conversations will appear here.
                </p>
              ) : (
                conversations.map((conversation) => {
                  const selected = parsedConversationId === conversation.id;
                  return (
                    <div
                      key={conversation.id}
                      className={`group flex items-center gap-1 rounded-xl transition ${
                        selected ? "bg-[#303030]" : "hover:bg-[#2a2a2a]"
                      }`}
                    >
                      <button
                        onClick={() => openConversation(conversation.id)}
                        title={conversation.title}
                        className="min-w-0 flex-1 px-3 py-2.5 text-left"
                      >
                        <span className="block truncate text-xs text-[#dddddd]">
                          {conversation.title || "New conversation"}
                        </span>
                        <span className="mt-1 block text-[10px] text-[#777777]">
                          {conversation.message_count} messages
                        </span>
                      </button>

                      <button
                        onClick={() => void removeConversation(conversation.id)}
                        title="Delete conversation"
                        aria-label={`Delete ${conversation.title || "conversation"}`}
                        className="mr-1 rounded-lg p-2 text-[#777777] opacity-100 transition hover:bg-[#414141] hover:text-red-300 sm:opacity-0 sm:group-hover:opacity-100"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* SIDEBAR FOOTER */}

          <div className="mt-auto">
            <div
              className={`mb-5 rounded-2xl border border-[#383838] bg-[#1a1a1a] p-4 ${
                sidebarCollapsed ? "lg:hidden" : ""
              }`}
            >
              <div className="mb-2 flex items-center gap-2 text-[#eeeeee]">
                <Sparkles size={16} />

                <span className="text-xs font-bold">
                  YOUR MARKET GUIDE
                </span>
              </div>

              <p className="mb-3 text-xs leading-5 text-[#a0a0a0]">
                Learn the market one question at a time.
              </p>

              <button
                onClick={() => handleNavigation("Ask GREEDY")}
                className="w-full rounded-lg bg-[#eeeeee] py-2 text-xs font-bold text-[#171717] transition hover:bg-white"
              >
                Start a conversation
              </button>
            </div>

            <button
              onClick={() => handleNavigation("Settings")}
              title={sidebarCollapsed ? "Settings" : undefined}
              className={`flex w-full items-center rounded-xl px-3 py-3 text-sm text-[#a0a0a0] transition hover:bg-[#2a2a2a] hover:text-white ${
                sidebarCollapsed ? "lg:justify-center" : "gap-3"
              }`}
            >
              <Settings size={18} />

              <span className={sidebarCollapsed ? "lg:hidden" : ""}>
                Settings
              </span>
            </button>

            <div
              className={`mt-3 flex items-center border-t border-[#303030] pt-4 ${
                sidebarCollapsed ? "lg:justify-center" : "gap-3"
              }`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#383838] text-sm font-bold text-white">
                GS
              </div>

              <div className={sidebarCollapsed ? "lg:hidden" : ""}>
                <p className="text-xs font-semibold text-[#eeeeee]">
                  Market Explorer
                </p>

                <p className="text-[10px] text-[#888888]">
                  Beginner level
                </p>
              </div>

              {!sidebarCollapsed && (
                <ChevronDown
                  className="ml-auto text-[#888888]"
                  size={15}
                />
              )}
            </div>
          </div>
        </aside>

        {/* MAIN CONTENT */}

        <section className="min-w-0 flex-1">

          {/* TOP HEADER: HIDDEN ON ASK GREEDY */}

          {currentNav !== "Ask GREEDY" ? (
            <header className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-[#303030] bg-[#000000]/95 px-4 backdrop-blur-xl md:px-7">

              <div className="flex items-center gap-3">

                {/* MOBILE SIDEBAR TOGGLE */}

                <button
                  onClick={toggleMobileMenu}
                  className="rounded-lg p-2 text-[#a0a0a0] transition hover:bg-[#000000] hover:text-white lg:hidden"
                  aria-label="Open sidebar"
                  title="Open sidebar"
                >
                  <Menu size={20} />
                </button>

                <div>
                  <p className="text-sm font-semibold text-[#eeeeee]">
                    {currentNav}
                  </p>

                  <p className="hidden text-[11px] text-[#888888] sm:block">
                    Your personal Indian stock market learning space
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button className="hidden items-center gap-2 rounded-xl border border-[#414141] bg-[#2a2a2a] px-3 py-2 text-xs text-[#a0a0a0] transition hover:bg-[#353535] sm:flex">
                  <Search size={15} />

                  Search stocks

                  <span className="text-[#777777]">âŒ˜ K</span>
                </button>

                <button
                  aria-label="Notifications"
                  className="rounded-xl border border-[#414141] p-2.5 text-[#a0a0a0] transition hover:bg-[#000000] hover:text-white"
                >
                  <Bell size={17} />
                </button>

                <div className="hidden h-8 w-8 items-center justify-center rounded-full bg-[#383838] text-xs font-bold text-white sm:flex">
                  GS
                </div>
              </div>
            </header>
          ) : (
            /* MOBILE MENU ACCESS FOR ASK GREEDY */

            <button
              onClick={toggleMobileMenu}
              aria-label="Open sidebar"
              className="fixed left-3 top-3 z-30 flex h-10 w-10 items-center justify-center rounded-lg bg-[#303030] text-white shadow-lg lg:hidden"
            >
              {mobileMenu ? <X size={20} /> : <Menu size={20} />}
            </button>
          )}

          {/* ASK GREEDY */}

          {currentNav === "Ask GREEDY" ? (
            <AskGreedyChat
              key={`ask-greedy-chat-${parsedConversationId ?? "new"}`}
              initialQuestion={questionFromUrl}
              initialConversationId={parsedConversationId}
              onConversationUpdated={() => void refreshConversations()}
            />
          ) : currentNav === "Explore & Discover" ? (
            <ExploreDiscover />
) : currentNav === "Portfolio Builder" ? (
            <PortfolioBuilder initialSelectedStock={stockFromUrl} />
          ) : currentNav === "Learn" ? (
            <LearnPage />
          ) : (

            /* DASHBOARD */

            <div className="mx-auto max-w-[1500px] p-5 md:p-8">

              {/* DASHBOARD HEADING */}

              <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <div className="mb-2 flex items-center gap-2 text-xs text-[#b0b0b0]">
                    <span className="h-2 w-2 rounded-full bg-[#aaaaaa]" />
                    YOUR MARKET LEARNING DASHBOARD
                  </div>

                  <h2 className="text-2xl font-bold tracking-tight text-[#eeeeee] md:text-3xl">
                    Understand the market.{" "}
                    <span className="text-[#999999]">
                      Think smarter.
                    </span>
                  </h2>

                  <p className="mt-2 text-sm text-[#999999]">
                    Explore NIFTY 50, discover opportunities and learn investing.
                  </p>
                </div>

                <button
                  onClick={() => handleNavigation("Ask GREEDY")}
                  className="flex items-center gap-2 rounded-xl bg-[#eeeeee] px-4 py-3 text-sm font-bold text-[#171717] transition hover:bg-white"
                >
                  <MessageSquare size={16} />
                  Ask GREEDY
                </button>
              </div>

              {/* DATA NOTICE */}

              <div className="mb-6 flex items-start gap-3 rounded-xl border border-[#555044] bg-[#302d25] p-3.5">
                <Activity
                  className="mt-0.5 shrink-0 text-[#e2c98a]"
                  size={17}
                />

                <p className="text-xs leading-5 text-[#d4c9ae]">
                  <strong className="text-[#f0d99e]">
                    Prototype preview:
                  </strong>{" "}
                  All market values and chart points on this screen are illustrative
                  sample data, not live market prices or investment recommendations.
                </p>
              </div>

              {/* MARKET CARDS */}

              <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MarketCard
                  label="NIFTY 50"
                  value="22,680.40"
                  change="+1.24%"
                  positive
                  icon={<TrendingUp size={18} />}
                />

                <MarketCard
                  label="SENSEX"
                  value="74,512.30"
                  change="+0.86%"
                  positive
                  icon={<Activity size={18} />}
                />

                <MarketCard
                  label="MARKET MOOD"
                  value="Positive"
                  change="Illustrative"
                  positive
                  icon={<Sparkles size={18} />}
                />

                <MarketCard
                  label="DATA STATUS"
                  value="Sample data"
                  change="Not live"
                  positive={false}
                  icon={<ShieldCheck size={18} />}
                />
              </div>

              {/* CHART AND GUIDE */}

              <div className="mb-6 grid grid-cols-1 gap-5 xl:grid-cols-3">

                {/* NIFTY CHART */}

                <div className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5 xl:col-span-2">
                  <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-[#eeeeee]">
                        NIFTY 50 Overview
                      </p>

                      <p className="mt-1 text-xs text-[#999999]">
                        Illustrative index movement
                      </p>
                    </div>

                    <div className="flex gap-1 rounded-lg bg-[#171717] p-1">
                      {periods.map((period) => (
                        <button
                          key={period}
                          onClick={() => setActivePeriod(period)}
                          className={`rounded-md px-3 py-1.5 text-[10px] font-semibold transition ${
                            activePeriod === period
                              ? "bg-[#eeeeee] text-[#171717]"
                              : "text-[#999999] hover:text-white"
                          }`}
                        >
                          {period}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mb-4">
                    <span className="text-3xl font-bold tracking-tight text-[#eeeeee]">
                      22,680.40
                    </span>

                    <span className="ml-3 text-sm font-semibold text-[#75b798]">
                      +278.20 (+1.24%)
                    </span>
                  </div>

                  <div className="h-[260px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData}>
                        <defs>
                          <linearGradient
                            id="marketGradient"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="#b0b0b0"
                              stopOpacity={0.22}
                            />

                            <stop
                              offset="95%"
                              stopColor="#b0b0b0"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>

                        <CartesianGrid
                          stroke="#ffffff"
                          strokeOpacity={0.07}
                          vertical={false}
                        />

                        <XAxis
                          dataKey="day"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#999999", fontSize: 11 }}
                          dy={10}
                        />

                        <YAxis
                          domain={["dataMin - 150", "dataMax + 150"]}
                          orientation="right"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#999999", fontSize: 10 }}
                          width={55}
                        />

                        <Tooltip
                          contentStyle={{
                            background: "#303030",
                            border: "1px solid #555555",
                            borderRadius: "10px",
                            color: "#fff",
                            fontSize: "12px",
                          }}
                        />

                        <Area
                          type="monotone"
                          dataKey="value"
                          stroke="#bdbdbd"
                          strokeWidth={2.5}
                          fill="url(#marketGradient)"
                          activeDot={{ r: 5, fill: "#eeeeee" }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  <p className="mt-2 text-[10px] text-[#888888]">
                    Sample chart Â· Period selector is a UI preview; data is not
                    connected to a market feed.
                  </p>
                </div>

                {/* GREEDY GUIDE */}

                <div className="relative overflow-hidden rounded-2xl border border-[#414141] bg-[#1a1a1a] p-5">
                  <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/[0.03] blur-3xl" />

                  <div className="relative">
                    <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-[#383838] text-[#eeeeee]">
                      <Sparkles size={22} />
                    </div>

                    <p className="text-xs font-bold tracking-widest text-[#bdbdbd]">
                      YOUR MARKET GUIDE
                    </p>

                    <h3 className="mt-3 text-xl font-bold leading-7 text-[#eeeeee]">
                      The market can be complicated. Learning doesn&apos;t have to be.
                    </h3>

                    <p className="mt-3 text-xs leading-6 text-[#a0a0a0]">
                      Ask questions about stocks, NIFTY 50, financial concepts
                      and investment research in simple language.
                    </p>

                    <div className="mt-6 space-y-2">
                      {[
                        "What is NIFTY 50?",
                        "How do I analyse a stock?",
                        "Explain risk in simple words",
                      ].map((question) => (
                        <button
                          key={question}
                          onClick={() => {
                            router.push(
                              `/?question=${encodeURIComponent(question)}`
                            );
                          }}
                          className="flex w-full items-center justify-between rounded-lg border border-[#414141] bg-[#171717] px-3 py-3 text-left text-xs text-[#d0d0d0] transition hover:bg-[#353535] hover:text-white"
                        >
                          {question}

                          <ArrowUpRight
                            size={14}
                            className="text-[#aaaaaa]"
                          />
                        </button>
                      ))}
                    </div>

                    <button
                      onClick={() => handleNavigation("Ask GREEDY")}
                      className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-[#eeeeee] py-3 text-sm font-bold text-[#171717] transition hover:bg-white"
                    >
                      <MessageSquare size={16} />
                      Start learning
                    </button>
                  </div>
                </div>
              </div>

              {/* STOCK WATCHLIST */}

              <div className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-[#eeeeee]">
                      Stock Watchlist Preview
                    </h3>

                    <p className="mt-1 text-xs text-[#999999]">
                      Selected NIFTY 50 companies Â· Sample values
                    </p>
                  </div>

                  <button
                    onClick={() => handleNavigation("Explore & Discover")}
                    className="text-xs font-semibold text-[#d0d0d0] hover:text-white"
                  >
                    Explore all
                    <ArrowUpRight className="ml-1 inline" size={13} />
                  </button>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[500px] text-left">
                    <thead>
                      <tr className="border-b border-[#414141] text-[10px] uppercase tracking-wider text-[#999999]">
                        <th className="pb-3 font-medium">Company</th>
                        <th className="pb-3 font-medium">Symbol</th>
                        <th className="pb-3 text-right font-medium">
                          Sample price (â‚¹)
                        </th>
                        <th className="pb-3 text-right font-medium">
                          Sample change
                        </th>
                      </tr>
                    </thead>

                    <tbody>
                      {stocks.map((stock) => (
                        <tr
                          key={stock.symbol}
                          className="border-b border-[#383838] last:border-0"
                        >
                          <td className="py-4 text-xs font-semibold text-[#eeeeee]">
                            <button
                              onClick={() =>
                                router.push(`/companies/${stock.symbol}`)
                              }
                              className="text-left transition hover:text-white hover:underline"
                              title={`View ${stock.name} company profile`}
                            >
                              {stock.name}
                            </button>
                          </td>

                          <td className="py-4 text-xs text-[#999999]">
                            {stock.symbol}
                          </td>

                          <td className="py-4 text-right text-xs font-medium text-[#eeeeee]">
                            {stock.price}
                          </td>

                          <td
                            className={`py-4 text-right text-xs font-semibold ${
                              stock.positive
                                ? "text-[#75b798]"
                                : "text-[#e18b8b]"
                            }`}
                          >
                            <span className="inline-flex items-center gap-1">
                              {stock.positive ? (
                                <ArrowUpRight size={13} />
                              ) : (
                                <ArrowDownRight size={13} />
                              )}

                              {stock.change}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* FOOTER */}

              <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 text-[10px] text-[#777777]">
                <span>
                  GREEDY STOCKS Â· Learn. Analyse. Understand.
                </span>

                <span>
                  Educational prototype Â· Not investment advice
                </span>
              </footer>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

// --------------------------------------------------
// PAGE WRAPPER
// --------------------------------------------------

export default function Home() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#000000] p-8 text-[#eeeeee]">
          Loading GREEDY STOCKS...
        </main>
      }
    >
      <HomeContent />
    </Suspense>
  );
}

// --------------------------------------------------
// REUSABLE MARKET CARD
// --------------------------------------------------

function MarketCard({
  label,
  value,
  change,
  positive,
  icon,
}: {
  label: string;
  value: string;
  change: string;
  positive: boolean;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5 transition hover:border-[#555555]">
      <div className="mb-5 flex items-center justify-between">
        <p className="text-[10px] font-bold tracking-widest text-[#999999]">
          {label}
        </p>

        <span className="text-[#aaaaaa]">{icon}</span>
      </div>

      <p className="text-2xl font-bold tracking-tight text-[#eeeeee]">
        {value}
      </p>

      <p
        className={`mt-2 text-xs font-semibold ${
          positive ? "text-[#75b798]" : "text-[#d5b477]"
        }`}
      >
        {change}
      </p>
    </div>
  );
}

