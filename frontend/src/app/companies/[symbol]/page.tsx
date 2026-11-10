
"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowUp,
  Building2,
  CalendarDays,
  RefreshCw,
  ShieldAlert,
  Database,
  TrendingUp,
  Layers3,
  BriefcaseBusiness
} from "lucide-react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CompanyProfile = {
  company: {
    symbol: string;
    company_name: string;
    isin?: string | null;
    exchange?: string | null;
    sector?: string | null;
  };
  price_coverage?: {
    first_price_date?: string | null;
    last_price_date?: string | null;
    observations?: number | null;
    total_observations?: number | null;
  };
  latest_price?: {
    trade_date?: string | null;
    close_price?: number | string | null;
    previous_close?: number | string | null;
    total_traded_volume?: number | string | null;
    total_traded_value?: number | string | null;
  } | null;
  corporate_actions?: Array<{
    action_type?: string;
    ex_date?: string | null;
    record_date?: string | null;
    effective_date?: string | null;
    description?: string | null;
    ratio?: string | null;
    dividend_amount?: number | string | null;
    source_name?: string | null;
  }>;
  identifiers?: Array<{
    identifier_type?: string;
    identifier_value?: string;
    valid_from?: string | null;
    valid_to?: string | null;
  }>;
  data_limitations?: string[] | Record<string, unknown>;
};

function formatDate(value?: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatNumber(value?: number | string | null) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) return String(value);

  return number.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  });
}

function formatCurrency(value?: number | string | null) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) return String(value);

  return `₹${number.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  })}`;
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-[#111827] p-5">
      <div className="mb-5 flex items-center gap-3">
        <span className="rounded-xl bg-white/5 p-2 text-cyan-400">
          {icon}
        </span>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
      </div>

      {children}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-sm text-gray-400">{label}</p>
      <p className="mt-2 text-xl font-bold text-white">{value}</p>

      {detail && (
        <p className="mt-1 text-xs text-gray-500">{detail}</p>
      )}
    </div>
  );
}

function CompanyProfileContent() {
  const params = useParams();
  const router = useRouter();

  const symbol = String(params.symbol || "").toUpperCase();

  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function fetchCompany() {
      setLoading(true);

      try {
        const response = await fetch(
          `${API_URL}/companies/${encodeURIComponent(symbol)}`,
          {
            signal: controller.signal,
            cache: "no-store",
          }
        );

        if (response.status === 404) {
          throw new Error(`Company ${symbol} was not found.`);
        }

        if (!response.ok) {
          throw new Error(
            `Unable to load company profile (${response.status}).`
          );
        }

        const result: CompanyProfile = await response.json();

        if (!result.company) {
          throw new Error("Unexpected company profile response.");
        }

        if (!controller.signal.aborted) {
          setProfile(result);
          setError("");
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }

        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Something went wrong."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void fetchCompany();

    return () => controller.abort();
  }, [symbol, retryCount]);

  const company = profile?.company;
  const coverage = profile?.price_coverage;
  const latest = profile?.latest_price;

  const actions = profile?.corporate_actions || [];
  const identifiers = profile?.identifiers || [];

  const limitations = Array.isArray(profile?.data_limitations)
    ? profile.data_limitations.map(String)
    : profile?.data_limitations
      ? Object.entries(profile.data_limitations).map(
          ([key, value]) => `${key}: ${String(value)}`
        )
      : [];

  function handleAskGreedy(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!company) return;

    const formData = new FormData(event.currentTarget);
    const question = String(formData.get("question") || "").trim();

    if (!question) return;

    const contextualQuestion =
      `Regarding ${company.company_name} (${company.symbol}): ${question}`;

    router.push(
      `/?question=${encodeURIComponent(contextualQuestion)}`
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[#080d18] p-6 text-white">
        <div className="mx-auto max-w-6xl animate-pulse">
          <div className="mb-6 h-8 w-48 rounded bg-white/10" />

          <div className="h-40 rounded-2xl bg-white/5" />

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-28 rounded-xl bg-white/5"
              />
            ))}
          </div>
        </div>
      </main>
    );
  }

  if (error || !profile || !company) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080d18] p-6 text-white">
        <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#111827] p-8 text-center">
          <ShieldAlert
            className="mx-auto mb-4 text-amber-400"
            size={38}
          />

          <h1 className="text-xl font-bold">
            Profile unavailable
          </h1>

          <p className="mt-3 text-sm text-gray-400">
            {error || "We couldn't retrieve this company profile."}
          </p>

          <div className="mt-6 flex justify-center gap-3">
            <button
              onClick={() => router.back()}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/5"
            >
              Go back
            </button>

            <button
              onClick={() => setRetryCount((count) => count + 1)}
              className="flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-black hover:bg-cyan-400"
            >
              <RefreshCw size={15} />
              Retry
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#080d18] px-4 py-6 text-white md:px-8">
      <div className="mx-auto max-w-6xl">
        <button
          onClick={() => router.back()}
          className="mb-7 flex items-center gap-2 text-sm text-gray-400 transition hover:text-white"
        >
          <ArrowLeft size={17} />
          Back
        </button>

        {/* COMPANY HEADER */}
        <div className="mb-7 rounded-2xl border border-white/10 bg-gradient-to-br from-[#14243b] to-[#101827] p-6 md:p-8">
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
            <div>
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-cyan-400">
                <Building2 size={15} />
                NIFTY 50 COMPANY PROFILE
              </div>

              <h1 className="text-3xl font-bold md:text-4xl">
                {company.company_name}
              </h1>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-gray-300">
                <span className="rounded-lg bg-cyan-400/10 px-3 py-1 font-semibold text-cyan-300">
                  {company.symbol}
                </span>

                <span>
                  {company.sector || "Sector unavailable"}
                </span>

                <span>•</span>

                <span>{company.exchange || "NSE"}</span>
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-black/20 p-5 md:min-w-48">
              <p className="text-sm text-gray-400">
                Latest recorded close
              </p>

              <p className="mt-2 text-3xl font-bold">
                {formatCurrency(latest?.close_price)}
              </p>

              <p className="mt-2 text-xs text-gray-500">
                As of {formatDate(latest?.trade_date)}
              </p>
            </div>
          </div>
        </div>

        <div className="mb-7 flex flex-wrap gap-3">
          <button
            onClick={() => {
              const key = "greedy-stocks-selected";
              const saved = JSON.parse(localStorage.getItem(key) || "[]") as string[];
              const updated = Array.from(new Set([...saved, company.symbol.toUpperCase()]));
              localStorage.setItem(key, JSON.stringify(updated));
              router.push(`/?addStock=${encodeURIComponent(company.symbol)}`);
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 text-sm font-bold text-[#07111f] transition hover:bg-cyan-300"
          >
            <BriefcaseBusiness size={17} />
            Add to Portfolio Builder
          </button>
        </div>
        {/* KEY METRICS */}
        <div className="mb-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Trading observations"
            value={formatNumber(
              coverage?.observations ??
                coverage?.total_observations
            )}
            detail="Available price records"
          />

          <Metric
            label="First recorded date"
            value={formatDate(coverage?.first_price_date)}
          />

          <Metric
            label="Latest recorded date"
            value={formatDate(coverage?.last_price_date)}
          />

          <Metric
            label="ISIN"
            value={company.isin || "Unavailable"}
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* LATEST MARKET DATA */}
          <Section
            title="Latest Market Data"
            icon={<TrendingUp size={19} />}
          >
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="Close price"
                value={formatCurrency(latest?.close_price)}
              />

              <Metric
                label="Previous close"
                value={formatCurrency(latest?.previous_close)}
              />

              <Metric
                label="Traded volume"
                value={formatNumber(
                  latest?.total_traded_volume
                )}
              />

              <Metric
                label="Traded value"
                value={formatCurrency(
                  latest?.total_traded_value
                )}
              />
            </div>
          </Section>

          {/* CORPORATE ACTIONS */}
          <Section
            title="Corporate Actions"
            icon={<CalendarDays size={19} />}
          >
            {actions.length === 0 ? (
              <p className="text-sm text-gray-400">
                No corporate action records are currently available.
              </p>
            ) : (
              <div className="space-y-3">
                {actions.map((action, index) => (
                  <div
                    key={`${action.action_type}-${action.ex_date}-${index}`}
                    className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-cyan-300">
                        {(action.action_type || "OTHER").replaceAll(
                          "_",
                          " "
                        )}
                      </span>

                      <span className="text-xs text-gray-400">
                        Ex-date: {formatDate(action.ex_date)}
                      </span>
                    </div>

                    <p className="mt-2 text-sm text-gray-300">
                      {action.description ||
                        "No additional description."}
                    </p>

                    {action.ratio && (
                      <p className="mt-1 text-xs text-gray-400">
                        Ratio: {action.ratio}
                      </p>
                    )}

                    {action.dividend_amount != null && (
                      <p className="mt-1 text-xs text-gray-400">
                        Dividend:{" "}
                        {formatCurrency(action.dividend_amount)}
                      </p>
                    )}

                    {action.source_name && (
                      <p className="mt-2 text-xs text-gray-500">
                        Source: {action.source_name}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* IDENTIFIERS */}
          <Section
            title="Company Identifiers"
            icon={<Layers3 size={19} />}
          >
            {identifiers.length === 0 ? (
              <p className="text-sm text-gray-400">
                No additional identifiers are available.
              </p>
            ) : (
              <div className="space-y-3">
                {identifiers.map((item, index) => (
                  <div
                    key={`${item.identifier_type}-${item.identifier_value}-${index}`}
                    className="flex flex-col gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-4 sm:flex-row sm:justify-between"
                  >
                    <span className="text-sm text-gray-400">
                      {item.identifier_type || "Identifier"}
                    </span>

                    <span className="text-sm font-semibold text-white">
                      {item.identifier_value || "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* DATA & METHODOLOGY */}
          <Section
            title="Data & Methodology"
            icon={<Database size={19} />}
          >
            <div className="space-y-3 text-sm text-gray-300">
              <p>
                <span className="text-gray-500">
                  Price basis:
                </span>{" "}
                Raw closing prices, unadjusted.
              </p>

              <p>
                <span className="text-gray-500">
                  Data source:
                </span>{" "}
                NSE historical price records stored in GREEDY STOCKS.
              </p>

              <p>
                <span className="text-gray-500">
                  Corporate actions:
                </span>{" "}
                Available records may cover only part of the
                historical period. Dividend adjustments are not
                included.
              </p>

              {limitations.length > 0 && (
                <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-4">
                  <p className="mb-2 flex items-center gap-2 font-semibold text-amber-300">
                    <ShieldAlert size={16} />
                    Data limitations
                  </p>

                  <ul className="list-disc space-y-1 pl-5 text-xs text-gray-400">
                    {limitations.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Section>
        </div>

        {/* SIMPLE CHATGPT-STYLE ASK GREEDY */}
        <div className="mx-auto mt-10 max-w-3xl">
          <div className="mb-4 text-center">
            <h2 className="text-xl font-semibold text-white">
              Ask GREEDY
            </h2>

            <p className="mt-2 text-sm text-gray-400">
              Ask anything about {company.company_name}.
            </p>
          </div>

          <form
            onSubmit={handleAskGreedy}
            className="flex items-end gap-3 rounded-2xl border border-white/10 bg-[#111827] p-3 shadow-lg transition focus-within:border-cyan-400/50"
          >
            <textarea
              name="question"
              rows={1}
              required
              placeholder={`Ask anything about ${company.symbol}...`}
              className="max-h-36 min-h-12 flex-1 resize-y bg-transparent px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-gray-500"
            />

            <button
              type="submit"
              aria-label="Send message to GREEDY"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-cyan-500 text-black transition hover:bg-cyan-400"
            >
              <ArrowUp size={20} />
            </button>
          </form>

          <p className="mt-3 text-center text-[11px] text-gray-500">
            GREEDY STOCKS can help explain historical company data.
          </p>
        </div>

        <p className="mt-8 text-center text-xs text-gray-600">
          GREEDY STOCKS · Educational research only · Not investment advice
        </p>
      </div>
    </main>
  );
}

export default function CompanyProfilePage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#080d18] p-8 text-white">
          Loading company profile...
        </main>
      }
    >
      <CompanyProfileContent />
    </Suspense>
  );
}
