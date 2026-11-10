
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertCircle,
  BrainCircuit,
  ExternalLink,
  MessageSquare,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const periods = ["1M", "3M", "6M", "1Y"] as const;

type Period = (typeof periods)[number];

type MarketIdea = {
  category: string;
  title: string;
  what: string;
  why: string;
  risk: string;
  explore: string;
  evidence: Record<string, unknown>;
  status: string;
  symbol?: string;
  company_symbol?: string;
};

type MarketIdeasResponse = {
  product: string;
  report_type: string;
  metadata: {
    index: string;
    period: string;
    snapshot_month: string;
    price_basis: string;
    dividend_adjusted: boolean;
    membership_basis: string;
    corporate_action_coverage: string;
    data_as_of: string | null;
    universe_size: number;
    calculated_companies: number;
    insufficient_data_companies: number;
    database_writes: boolean;
    interpretation: string;
  };
  ideas: MarketIdea[];
  disclosures: string[];
};

const categoryInfo: Record<
  string,
  {
    label: string;
    description: string;
    icon: typeof TrendingUp;
  }
> = {
  PERFORMANCE_STANDOUTS: {
    label: "Performance Standouts",
    description: "Companies with stronger historical returns.",
    icon: TrendingUp,
  },

  RISK_AND_STABILITY: {
    label: "Risk & Stability",
    description: "Historical volatility and drawdown comparisons.",
    icon: ShieldAlert,
  },

  SECTOR_PERFORMANCE: {
    label: "Sector Performance",
    description: "Historical performance across NIFTY 50 sector constituents.",
    icon: Activity,
  },

  GREEDY_PICKS: {
    label: "Greedy Lab Experiments",
    description: "Historical selections from the experimental Greedy algorithm.",
    icon: BrainCircuit,
  },

  FUNDAMENTAL_RESEARCH: {
    label: "Fundamental Research",
    description: "Availability of verified company fundamental data.",
    icon: Sparkles,
  },
};

// --------------------------------------------------
// COMPANY SYMBOL RESOLUTION
// --------------------------------------------------

function getCompanySymbol(idea: MarketIdea): string | null {
  const evidence = idea.evidence || {};

  const possibleSymbols = [
    idea.symbol,
    idea.company_symbol,
    evidence.symbol,
    evidence.company_symbol,
    evidence.stock_symbol,
    evidence.ticker,
  ];

  for (const value of possibleSymbols) {
    if (typeof value !== "string") continue;

    const symbol = value.trim().toUpperCase();

    if (/^[A-Z0-9&-]{2,30}$/.test(symbol)) {
      return symbol;
    }
  }

  const excludedTerms = new Set([
    "NIFTY",
    "NSE",
    "BSE",
    "INDIA",
    "STOCK",
    "STOCKS",
    "RISK",
    "SECTOR",
    "GREEDY",
    "PICKS",
    "TOP",
    "BEST",
    "THE",
    "AND",
    "FOR",
    "WITH",
    "ONE",
    "YEAR",
    "MONTH",
  ]);

  const matches =
    idea.title.match(/\b[A-Z][A-Z0-9&-]{1,19}\b/g) || [];

  const candidate = matches.find(
    (item) => !excludedTerms.has(item)
  );

  return candidate || null;
}

// --------------------------------------------------
// FORMATTING
// --------------------------------------------------

function formatEvidence(value: unknown): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    return Number.isInteger(value)
      ? String(value)
      : value.toFixed(4);
  }

  return String(value);
}

function evidenceLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/Pct/g, "(%)");
}

// --------------------------------------------------
// EVIDENCE PANEL
// --------------------------------------------------

function EvidencePanel({
  evidence,
}: {
  evidence: Record<string, unknown>;
}) {
  const excluded = new Set(["source"]);

  const entries = Object.entries(evidence).filter(
    ([key, value]) =>
      !excluded.has(key) &&
      value !== null &&
      value !== undefined &&
      typeof value !== "object"
  );

  if (!entries.length) return null;

  return (
    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="rounded-xl border border-[#303030] bg-[#1a1a1a] p-3"
        >
          <p className="text-[10px] text-[#a0a0a0]">
            {evidenceLabel(key)}
          </p>

          <p className="mt-1 break-words text-xs font-semibold text-[#ececec]">
            {formatEvidence(value)}
          </p>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------
// IDEA CARD
// --------------------------------------------------

function IdeaCard({
  idea,
  onExploreWithGreedy,
  onOpenCompany,
}: {
  idea: MarketIdea;
  onExploreWithGreedy: (idea: MarketIdea) => void;
  onOpenCompany: (symbol: string) => void;
}) {
  const isUnavailable = idea.status !== "AVAILABLE";
  const companySymbol = getCompanySymbol(idea);

  return (
    <article className="rounded-2xl border border-[#303030] bg-[#000000] p-5 transition duration-200 hover:bg-[#000000] hover:border-[#555555]">
      {/* CARD TITLE */}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold leading-6 text-[#ececec]">
            {idea.title}
          </h4>

          <span
            className={`mt-3 inline-flex rounded-full border px-2.5 py-1 text-[10px] font-semibold ${
              isUnavailable
                ? "border-[#66573a] bg-[#393225] text-[#e3c78b]"
                : "border-[#4a4a4a] bg-[#303030] text-[#d4d4d4]"
            }`}
          >
            {idea.status.replace(/_/g, " ")}
          </span>
        </div>

        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#1a1a1a] text-[#d0d0d0]">
          {idea.category === "PERFORMANCE_STANDOUTS" && (
            <TrendingUp size={18} />
          )}

          {idea.category === "RISK_AND_STABILITY" && (
            <ShieldAlert size={18} />
          )}

          {idea.category === "SECTOR_PERFORMANCE" && (
            <Activity size={18} />
          )}

          {idea.category === "GREEDY_PICKS" && (
            <BrainCircuit size={18} />
          )}

          {idea.category === "FUNDAMENTAL_RESEARCH" && (
            <Sparkles size={18} />
          )}
        </div>
      </div>

      {/* WHAT */}

      <div className="mt-5 space-y-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[#a0a0a0]">
            What
          </p>

          <p className="mt-1.5 text-xs leading-6 text-[#d4d4d4]">
            {idea.what}
          </p>
        </div>

        {/* WHY */}

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[#a0a0a0]">
            Why it matters
          </p>

          <p className="mt-1.5 text-xs leading-6 text-[#b4b4b4]">
            {idea.why}
          </p>
        </div>

        {/* RISK */}

        <div className="rounded-xl border border-[#514b3c] bg-[#292721] p-3.5">
          <div className="flex items-center gap-2 text-[#e1c98e]">
            <AlertCircle size={14} />

            <span className="text-[10px] font-semibold uppercase tracking-wider">
              Risk to understand
            </span>
          </div>

          <p className="mt-2 text-xs leading-5 text-[#d1c7ad]">
            {idea.risk}
          </p>
        </div>

        {/* EVIDENCE */}

        <EvidencePanel evidence={idea.evidence} />

        {/* EXPLORE */}

        <div className="border-t border-[#303030] pt-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[#bdbdbd]">
            Explore further
          </p>

          <p className="mt-1.5 text-xs leading-5 text-[#b4b4b4]">
            {idea.explore}
          </p>

          {/* NEW: EXPLORE WITH GREEDY */}

          <button
            onClick={() => onExploreWithGreedy(idea)}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-[#eeeeee] px-4 py-2.5 text-xs font-semibold text-[#171717] transition hover:bg-white"
          >
            <MessageSquare size={14} />
            Explore with GREEDY
          </button>

          {/* EXISTING COMPANY PROFILE LINK */}

          {companySymbol && (
            <button
              onClick={() => onOpenCompany(companySymbol)}
              className="mt-3 ml-2 inline-flex items-center gap-2 rounded-xl border border-[#555555] bg-[#303030] px-3.5 py-2.5 text-xs font-semibold text-[#eeeeee] transition hover:bg-[#3a3a3a] hover:border-[#777777]"
            >
              View {companySymbol} company profile
              <ExternalLink size={13} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

// --------------------------------------------------
// METADATA CARD
// --------------------------------------------------

function MetadataCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-[#303030] bg-[#000000] p-4 transition hover:bg-[#000000]">
      <p className="text-[9px] font-semibold tracking-widest text-[#999999]">
        {label}
      </p>

      <p className="mt-2 break-words text-xs font-semibold text-[#ececec]">
        {value}
      </p>
    </div>
  );
}

// --------------------------------------------------
// MAIN MARKET IDEAS COMPONENT
// --------------------------------------------------

export default function MarketIdeasPanel() {
  const router = useRouter();

  const [period, setPeriod] = useState<Period>("3M");
  const [data, setData] = useState<MarketIdeasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  // ------------------------------------------------
  // FETCH MARKET IDEAS
  // ------------------------------------------------

  useEffect(() => {
    const controller = new AbortController();

    async function fetchIdeas() {
      try {
        const response = await fetch(
          `${API_URL}/market-ideas?period=${period}&top_n=5`,
          {
            method: "GET",
            cache: "no-store",
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          const errorBody = await response.json().catch(() => null);

          throw new Error(
            errorBody?.detail ||
              `Market Ideas request failed (${response.status}).`
          );
        }

        const result: MarketIdeasResponse = await response.json();

        if (!Array.isArray(result.ideas) || !result.metadata) {
          throw new Error("The API returned an unexpected response.");
        }

        if (!controller.signal.aborted) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (
          controller.signal.aborted ||
          (err instanceof Error && err.name === "AbortError")
        ) {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "Unable to load Market Ideas."
        );

        setData(null);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void fetchIdeas();

    return () => {
      controller.abort();
    };
  }, [period, retryCount]);

  // ------------------------------------------------
  // HANDLERS
  // ------------------------------------------------

  const handlePeriodChange = (nextPeriod: Period) => {
    if (nextPeriod === period) return;

    setLoading(true);
    setError(null);
    setPeriod(nextPeriod);
  };

  const handleRefresh = () => {
    setLoading(true);
    setError(null);
    setRetryCount((count) => count + 1);
  };

  const handleOpenCompany = (symbol: string) => {
    router.push(`/companies/${encodeURIComponent(symbol)}`);
  };

  // NEW: BUILD CONTEXTUAL QUESTION AND OPEN ASK GREEDY

  const handleExploreWithGreedy = (idea: MarketIdea) => {
    const symbol = getCompanySymbol(idea);

    const evidenceText = Object.entries(idea.evidence || {})
      .filter(
        ([, value]) =>
          value !== null &&
          value !== undefined &&
          typeof value !== "object"
      )
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join("\n");

    const question = [
      `Help me understand this NIFTY 50 Market Idea in simple language.`,
      "",
      `Company: ${symbol || "Not specified"}`,
      `Insight: ${idea.title}`,
      `Category: ${idea.category}`,
      `Analysis period: ${period}`,
      `Data as of: ${data?.metadata.data_as_of || "Not specified"}`,
      "",
      `WHAT:\n${idea.what}`,
      "",
      `WHY IT MATTERS:\n${idea.why}`,
      "",
      `RISK:\n${idea.risk}`,
      "",
      `EXPLORE FURTHER:\n${idea.explore}`,
      "",
      `AVAILABLE EVIDENCE:\n${evidenceText || "No additional evidence supplied."}`,
      "",
      "Please explain what this insight means, how to interpret the evidence, what its limitations are, and what a beginner should investigate next. Do not treat historical performance as a prediction or investment recommendation.",
    ].join("\n");

    router.push(`/?question=${encodeURIComponent(question)}`);
  };

  // ------------------------------------------------
  // GROUP IDEAS
  // ------------------------------------------------

  const groupedIdeas = (data?.ideas || []).reduce<
    Record<string, MarketIdea[]>
  >((groups, idea) => {
    if (!groups[idea.category]) {
      groups[idea.category] = [];
    }

    groups[idea.category].push(idea);

    return groups;
  }, {});

  return (
    <div className="min-h-[calc(100vh-76px)] bg-[#000000]">
      <div className="mx-auto max-w-[1500px] p-5 md:p-8">

        {/* PAGE HEADING */}

        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold tracking-wider text-[#bdbdbd]">
              <Sparkles size={15} />
              EVIDENCE-BASED NIFTY 50 RESEARCH
            </div>

            <h2 className="text-2xl font-semibold tracking-tight text-[#ececec] md:text-3xl">
              Market Ideas
              <span className="text-[#999999]">. Backed by evidence.</span>
            </h2>

            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#a0a0a0]">
              Explore historical performance, risk, sector behaviour and
              experimental algorithmic selections. Understand the evidence
              before drawing conclusions.
            </p>
          </div>

          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-2 rounded-xl border border-[#303030] bg-[#1a1a1a] px-4 py-3 text-xs font-semibold text-[#dedede] transition hover:bg-[#383838] hover:text-white disabled:opacity-50"
          >
            <RefreshCw
              size={15}
              className={loading ? "animate-spin" : ""}
            />
            Refresh insights
          </button>
        </div>

        {/* PERIOD SELECTOR */}

        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[#303030] bg-[#000000] p-4">
          <div>
            <p className="text-sm font-semibold text-[#ececec]">
              Historical analysis period
            </p>

            <p className="mt-1 text-xs text-[#999999]">
              Change the period to regenerate insights from historical data.
            </p>
          </div>

          <div className="flex gap-1 rounded-xl bg-[#1a1a1a] p-1">
            {periods.map((item) => (
              <button
                key={item}
                onClick={() => handlePeriodChange(item)}
                aria-pressed={period === item}
                className={`rounded-lg px-4 py-2 text-xs font-semibold transition ${
                  period === item
                    ? "bg-[#eeeeee] text-[#171717]"
                    : "text-[#b0b0b0] hover:bg-[#414141] hover:text-white"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        {/* LOADING */}

        {loading && (
          <div className="rounded-2xl border border-[#303030] bg-[#000000] p-12 text-center">
            <RefreshCw
              size={25}
              className="mx-auto animate-spin text-[#d0d0d0]"
            />

            <p className="mt-4 text-sm font-semibold text-[#eeeeee]">
              Analysing NIFTY 50 historical data...
            </p>

            <p className="mt-2 text-xs text-[#999999]">
              Generating evidence-based Market Ideas.
            </p>
          </div>
        )}

        {/* ERROR */}

        {!loading && error && (
          <div className="rounded-2xl border border-[#604444] bg-[#292222] p-6">
            <div className="flex items-center gap-2 text-[#e6a2a2]">
              <AlertCircle size={19} />

              <p className="text-sm font-semibold">
                Unable to load Market Ideas
              </p>
            </div>

            <p className="mt-3 text-xs leading-6 text-[#c7aaaa]">
              {error}
            </p>

            <p className="mt-2 text-xs text-[#a58f8f]">
              Check that the GREEDY STOCKS FastAPI backend is running on port
              8000.
            </p>

            <button
              onClick={handleRefresh}
              className="mt-5 rounded-xl bg-[#eeeeee] px-4 py-2.5 text-xs font-semibold text-[#171717] transition hover:bg-white"
            >
              Try again
            </button>
          </div>
        )}

        {/* SUCCESSFUL RESPONSE */}

        {!loading && !error && data && (
          <>
            {/* METADATA */}

            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetadataCard
                label="INDEX"
                value={data.metadata.index}
              />

              <MetadataCard
                label="COMPANIES CALCULATED"
                value={`${data.metadata.calculated_companies}/${data.metadata.universe_size}`}
              />

              <MetadataCard
                label="DATA AS OF"
                value={data.metadata.data_as_of || "Unavailable"}
              />

              <MetadataCard
                label="PRICE BASIS"
                value={data.metadata.price_basis || "Unavailable"}
              />
            </div>

            {/* DATA LIMITATIONS */}

            <div className="mb-7 rounded-2xl border border-[#514b3c] bg-[#292721] p-4">
              <div className="flex items-center gap-2 text-[#e1c98e]">
                <AlertCircle size={16} />

                <p className="text-xs font-semibold">
                  Important data limitations
                </p>
              </div>

              <div className="mt-3 grid gap-2 text-xs text-[#d1c7ad] sm:grid-cols-2">
                <p>
                  Corporate-action coverage:{" "}
                  {data.metadata.corporate_action_coverage}
                </p>

                <p>
                  Dividend adjusted:{" "}
                  {data.metadata.dividend_adjusted ? "Yes" : "No"}
                </p>

                <p>
                  Membership basis:{" "}
                  {data.metadata.membership_basis}
                </p>

                <p>
                  Historical daily membership reconstructed: No
                </p>
              </div>
            </div>

            {/* INSIGHT CATEGORIES */}

            <div className="space-y-10">
              {Object.entries(categoryInfo).map(([category, info]) => {
                const ideas = groupedIdeas[category] || [];

                if (!ideas.length) return null;

                const Icon = info.icon;

                return (
                  <section key={category}>
                    <div className="mb-4 flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#303030] bg-[#1a1a1a] text-[#dedede]">
                        <Icon size={19} />
                      </div>

                      <div>
                        <h3 className="text-sm font-semibold text-[#eeeeee]">
                          {info.label}
                        </h3>

                        <p className="mt-1 text-xs text-[#999999]">
                          {info.description}
                        </p>
                      </div>

                      <span className="ml-auto rounded-lg border border-[#303030] bg-[#1a1a1a] px-2.5 py-1 text-[10px] text-[#bdbdbd]">
                        {ideas.length} insights
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      {ideas.map((idea, index) => (
                        <IdeaCard
                          key={`${idea.category}-${index}-${idea.title}`}
                          idea={idea}
                          onOpenCompany={handleOpenCompany}
                          onExploreWithGreedy={handleExploreWithGreedy}
                        />
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>

            {/* DISCLOSURES */}

            <div className="mt-9 rounded-2xl border border-[#303030] bg-[#000000] p-5">
              <div className="flex items-center gap-2">
                <ShieldAlert size={17} className="text-[#c5b58c]" />

                <h3 className="text-sm font-semibold text-[#eeeeee]">
                  Research disclosures
                </h3>
              </div>

              <ul className="mt-4 space-y-2">
                {data.disclosures.map((disclosure, index) => (
                  <li
                    key={index}
                    className="flex gap-2 text-xs leading-5 text-[#a0a0a0]"
                  >
                    <span className="text-[#bdbdbd]">â€¢</span>
                    {disclosure}
                  </li>
                ))}
              </ul>
            </div>

            <p className="mt-6 text-center text-[10px] leading-5 text-[#777777]">
              GREEDY STOCKS Â· Historical research and education only Â·
              Not investment advice
            </p>
          </>
        )}
      </div>
    </div>
  );
}


