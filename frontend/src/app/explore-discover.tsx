"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity, ArrowUpRight, Building2, Check, Compass,
  Search, SlidersHorizontal, TrendingUp, X
} from "lucide-react";
import MarketIdeasPanel from "./market-ideas";
import SectorExplorer from "./sector-explorer";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
type Period = "1M" | "3M" | "6M" | "1Y";
type Tab = "overview" | "explorer" | "comparison" | "opportunities";

type Company = {
  symbol: string;
  company_name: string;
  weightage: number | null;
  period_return_pct: number | null;
};

type Sector = {
  sector_id: number;
  sector_name: string;
  companies: Company[];
  company_count: number;
  average_constituent_return_pct: number | null;
};

type SectorResponse = {
  data_as_of: string;
  company_count: number;
  sector_count: number;
  sectors: Sector[];
};

const periods: Period[] = ["1M", "3M", "6M", "1Y"];

export default function ExploreDiscover() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [period, setPeriod] = useState<Period>("3M");
  const [data, setData] = useState<SectorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("ALL");
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (tab !== "explorer" && tab !== "comparison") return;

    const controller = new AbortController();
    setLoading(true);
    setError("");

    fetch(`${API_URL}/sectors?period=${period}`, {
      cache: "no-store",
      signal: controller.signal
    })
      .then(async response => {
        if (!response.ok) throw new Error(`Stock data request failed (${response.status})`);
        return response.json() as Promise<SectorResponse>;
      })
      .then(result => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch(err => {
        if (!controller.signal.aborted && err.name !== "AbortError") {
          setError(err.message || "Unable to load stock data.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [tab, period]);

  const companies = useMemo(() => {
    const map = new Map<string, Company & { sector: string }>();
    (data?.sectors || []).forEach(sector => {
      sector.companies.forEach(company => {
        map.set(company.symbol, { ...company, sector: sector.sector_name });
      });
    });
    return [...map.values()].sort((a, b) =>
      a.company_name.localeCompare(b.company_name)
    );
  }, [data]);

  const sectors = useMemo(
    () => [...new Set(companies.map(company => company.sector))].sort(),
    [companies]
  );

  const filtered = companies.filter(company => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query ||
      company.company_name.toLowerCase().includes(query) ||
      company.symbol.toLowerCase().includes(query);
    const matchesSector = sectorFilter === "ALL" || company.sector === sectorFilter;
    return matchesSearch && matchesSector;
  });

  const compared = selected
    .map(symbol => companies.find(company => company.symbol === symbol))
    .filter((company): company is NonNullable<typeof company> => Boolean(company));

  function toggleSelected(symbol: string) {
    setSelected(previous => previous.includes(symbol)
      ? previous.filter(item => item !== symbol)
      : previous.length < 5 ? [...previous, symbol] : previous
    );
  }

  function askGreedy(company: Company & { sector?: string }) {
    const question = `Help me research ${company.company_name} (${company.symbol}) in simple language. Its ${period} historical price return in the available sector data is ${company.period_return_pct ?? "unavailable"}%. Explain what this metric means, its limitations, and what else I should investigate. Do not treat historical performance as a prediction or investment recommendation.`;
    router.push(`/?question=${encodeURIComponent(question)}`);
  }

  const tabs: { id: Tab; label: string; description: string }[] = [
    { id: "overview", label: "Market Overview", description: "Index sectors and market trends" },
    { id: "explorer", label: "Stock Explorer", description: "Search and investigate companies" },
    { id: "comparison", label: "Stock Comparison", description: "Compare up to five companies" },
    { id: "opportunities", label: "Discover Opportunities", description: "Evidence-based research leads" }
  ];

  return (
    <div className="min-h-[calc(100vh-76px)] bg-[#000000]">
      <div className="mx-auto max-w-[1500px] p-5 md:p-8">
        <div className="mb-7">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wider text-[#bdbdbd]">
            <Compass size={15} /> RESEARCH WORKSPACE
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[#eeeeee] md:text-3xl">
            Explore & Discover
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#999999]">
            Discover companies, understand market behaviour, compare historical performance and investigate research opportunities.
          </p>
        </div>

        <div className="mb-7 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {tabs.map(item => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`rounded-xl border p-3 text-left transition ${
                tab === item.id
                  ? "border-[#aaaaaa] bg-[#303030]"
                  : "border-[#303030] bg-[#1a1a1a] hover:bg-[#000000]"
              }`}
            >
              <span className={`block text-xs font-semibold ${
                tab === item.id ? "text-white" : "text-[#cccccc]"
              }`}>{item.label}</span>
              <span className="mt-1 block text-[10px] text-[#888888]">{item.description}</span>
            </button>
          ))}
        </div>

        {tab === "overview" && <SectorExplorer />}
        {tab === "opportunities" && <MarketIdeasPanel />}

        {(tab === "explorer" || tab === "comparison") && (
          <>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-[#eeeeee]">
                  {tab === "explorer" ? "NIFTY 50 Stock Explorer" : "Compare Companies"}
                </h2>
                <p className="mt-1 text-xs text-[#888888]">
                  {data ? `${companies.length} companies in the available latest sector snapshot` : "Loading company data"}
                </p>
              </div>
              <div className="flex gap-1 rounded-xl border border-[#303030] bg-[#1a1a1a] p-1">
                {periods.map(item => (
                  <button
                    key={item}
                    onClick={() => setPeriod(item)}
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                      period === item ? "bg-[#eeeeee] text-[#171717]" : "text-[#999999] hover:text-white"
                    }`}
                  >{item}</button>
                ))}
              </div>
            </div>

            {error && (
              <div className="mb-5 rounded-xl border border-red-900 bg-[#352222] p-4 text-sm text-red-200">
                {error}
                <button onClick={() => setTab("overview")} className="ml-3 underline">Back to overview</button>
              </div>
            )}

            {loading && (
              <div className="rounded-xl border border-[#303030] bg-[#1a1a1a] p-10 text-center text-sm text-[#aaaaaa]">
                Loading company data...
              </div>
            )}

            {!loading && !error && data && tab === "explorer" && (
              <>
                <div className="mb-5 grid gap-3 md:grid-cols-[1fr_240px]">
                  <div className="relative">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#888888]" />
                    <input
                      value={search}
                      onChange={event => setSearch(event.target.value)}
                      placeholder="Search company name or symbol..."
                      className="w-full rounded-xl border border-[#414141] bg-[#1a1a1a] py-3 pl-10 pr-4 text-sm text-white outline-none focus:border-[#888888]"
                    />
                  </div>
                  <div className="relative">
                    <SlidersHorizontal size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#888888]" />
                    <select
                      value={sectorFilter}
                      onChange={event => setSectorFilter(event.target.value)}
                      className="w-full appearance-none rounded-xl border border-[#414141] bg-[#1a1a1a] py-3 pl-9 pr-3 text-xs text-white outline-none"
                    >
                      <option value="ALL">All sectors</option>
                      {sectors.map(sector => <option key={sector} value={sector}>{sector}</option>)}
                    </select>
                  </div>
                </div>

                <p className="mb-3 text-xs text-[#888888]">{filtered.length} matching companies</p>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {filtered.map(company => (
                    <article key={company.symbol} className="rounded-xl border border-[#303030] bg-[#1a1a1a] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-white">{company.company_name}</h3>
                          <p className="mt-1 text-xs text-[#999999]">{company.symbol} · {company.sector}</p>
                        </div>
                        <Building2 size={18} className="shrink-0 text-[#999999]" />
                      </div>
                      <div className="mt-4 flex items-end justify-between">
                        <div>
                          <p className="text-[10px] text-[#888888]">{period} historical price return</p>
                          <p className={`mt-1 text-lg font-bold ${
                            company.period_return_pct === null ? "text-[#888888]" :
                            company.period_return_pct >= 0 ? "text-[#75c99b]" : "text-[#ed8989]"
                          }`}>
                            {company.period_return_pct === null ? "N/A" :
                              `${company.period_return_pct > 0 ? "+" : ""}${company.period_return_pct.toFixed(2)}%`}
                          </p>
                        </div>
                        <p className="text-right text-[10px] text-[#888888]">
                          Weight<br />{company.weightage == null ? "N/A" : `${company.weightage.toFixed(2)}%`}
                        </p>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          onClick={() => router.push(`/companies/${encodeURIComponent(company.symbol)}`)}
                          className="rounded-lg border border-[#555555] px-3 py-2 text-[11px] font-semibold text-white hover:bg-[#383838]"
                        >Company profile <ArrowUpRight size={12} className="ml-1 inline" /></button>
                        <button
                          onClick={() => askGreedy(company)}
                          className="rounded-lg bg-[#eeeeee] px-3 py-2 text-[11px] font-semibold text-[#171717] hover:bg-white"
                        >Ask GREEDY</button>
                        <button
                          onClick={() => toggleSelected(company.symbol)}
                          className="rounded-lg border border-[#555555] px-3 py-2 text-[11px] text-[#cccccc] hover:bg-[#383838]"
                        >{selected.includes(company.symbol) ? <><Check size={12} className="mr-1 inline" /> Selected</> : "Compare"}</button>
                      </div>
                    </article>
                  ))}
                </div>
                {filtered.length === 0 && (
                  <div className="rounded-xl border border-[#303030] p-8 text-center text-sm text-[#999999]">No companies match your search.</div>
                )}
              </>
            )}

            {!loading && !error && data && tab === "comparison" && (
              <>
                <div className="mb-5 rounded-xl border border-[#303030] bg-[#1a1a1a] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-white">Select up to 5 companies</p>
                    <p className="text-xs text-[#999999]">{selected.length}/5 selected</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {companies.map(company => (
                      <button
                        key={company.symbol}
                        onClick={() => toggleSelected(company.symbol)}
                        className={`rounded-lg border px-3 py-2 text-xs ${
                          selected.includes(company.symbol)
                            ? "border-[#aaaaaa] bg-[#444444] text-white"
                            : "border-[#444444] text-[#bbbbbb] hover:bg-[#2a2a2a]"
                        }`}
                      >
                        {selected.includes(company.symbol) && <Check size={12} className="mr-1 inline" />}
                        {company.symbol}
                      </button>
                    ))}
                  </div>
                </div>

                {compared.length > 0 ? (
                  <div className="overflow-x-auto rounded-xl border border-[#303030]">
                    <table className="w-full min-w-[600px] text-left">
                      <thead className="bg-[#303030] text-[10px] uppercase text-[#999999]">
                        <tr>
                          <th className="px-4 py-3">Company</th>
                          <th className="px-4 py-3">Sector</th>
                          <th className="px-4 py-3 text-right">{period} return</th>
                          <th className="px-4 py-3 text-right">Weight</th>
                          <th className="px-4 py-3 text-right">Profile</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compared.map(company => (
                          <tr key={company.symbol} className="border-t border-[#303030] text-xs">
                            <td className="px-4 py-4">
                              <p className="font-semibold text-white">{company.company_name}</p>
                              <p className="mt-1 text-[#888888]">{company.symbol}</p>
                            </td>
                            <td className="px-4 py-4 text-[#bbbbbb]">{company.sector}</td>
                            <td className={`px-4 py-4 text-right font-semibold ${
                              company.period_return_pct == null ? "text-[#888888]" :
                              company.period_return_pct >= 0 ? "text-[#75c99b]" : "text-[#ed8989]"
                            }`}>
                              {company.period_return_pct == null ? "N/A" :
                                `${company.period_return_pct > 0 ? "+" : ""}${company.period_return_pct.toFixed(2)}%`}
                            </td>
                            <td className="px-4 py-4 text-right text-[#bbbbbb]">
                              {company.weightage == null ? "N/A" : `${company.weightage.toFixed(2)}%`}
                            </td>
                            <td className="px-4 py-4 text-right">
                              <button onClick={() => router.push(`/companies/${encodeURIComponent(company.symbol)}`)} className="text-[#dddddd] hover:underline">Open</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-[#555555] p-10 text-center text-sm text-[#999999]">
                    Select companies above to compare their available historical returns.
                  </div>
                )}

                <div className="mt-5 rounded-xl border border-[#514b3c] bg-[#292721] p-4 text-xs leading-5 text-[#d1c7ad]">
                  Comparison currently uses the sector API's available period price returns and snapshot weights. Company-level volatility, Sharpe ratio, drawdown, dividend-adjusted returns and historical daily membership are not provided by this endpoint.
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
