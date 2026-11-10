"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  Building2,
  ChevronRight,
  Compass,
  RefreshCw,
  Search,
  Sparkles,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Period = "1M" | "3M" | "6M" | "1Y";

interface Company {
  symbol: string;
  company_name: string;
  weightage: number | null;
  start_date: string;
  end_date: string;
  period_return_pct: number | null;
}

interface Sector {
  sector_id: number;
  sector_name: string;
  sector_description: string | null;
  companies: Company[];
  company_count: number;
  companies_with_price_data: number;
  average_constituent_return_pct: number | null;
  data_coverage_pct: number;
}

interface SectorResponse {
  index: string;
  period: Period;
  snapshot_month: string;
  data_as_of: string;
  comparison_target_date: string;
  sector_count: number;
  company_count: number;
  sectors: Sector[];
  methodology: {
    membership_basis: string;
    return_method: string;
    price_basis: string;
    return_type: string;
    dividend_adjusted: boolean;
    official_sector_index: boolean;
    database_writes: boolean;
  };
  limitations: string[];
}

const periods: Period[] = ["1M", "3M", "6M", "1Y"];

function formatReturn(value: number | null | undefined) {
  if (value === null || value === undefined) return "N/A";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatDate(value?: string) {
  if (!value) return "Unavailable";

  return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function ReturnValue({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-[#888888]">N/A</span>;
  }

  const positive = value >= 0;

  return (
    <span
      className={`font-semibold tabular-nums ${
        positive ? "text-[#75c99b]" : "text-[#ed8989]"
      }`}
    >
      {formatReturn(value)}
    </span>
  );
}

export default function SectorExplorer() {
  const router = useRouter();

  const [period, setPeriod] = useState<Period>("3M");
  const [data, setData] = useState<SectorResponse | null>(null);
  const [selectedSector, setSelectedSector] = useState<Sector | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loadedPeriod, setLoadedPeriod] = useState<Period | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/sectors?period=${period}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        return response.json() as Promise<SectorResponse>;
      })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setLoadedPeriod(period);
        setSelectedSector(null);
        setError("");
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load sector information."
        );
        setLoadedPeriod(period);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [period, refreshKey]);

  const isLoading = loading || loadedPeriod !== period;

  const sortedSectors = useMemo(() => {
    if (!data) return [];

    return [...data.sectors].sort((a, b) => {
      const aValue = a.average_constituent_return_pct;
      const bValue = b.average_constituent_return_pct;

      if (aValue === null) return 1;
      if (bValue === null) return -1;

      return bValue - aValue;
    });
  }, [data]);

  const filteredSectors = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return sortedSectors;

    return sortedSectors.filter(
      (sector) =>
        sector.sector_name.toLowerCase().includes(query) ||
        sector.companies.some(
          (company) =>
            company.company_name.toLowerCase().includes(query) ||
            company.symbol.toLowerCase().includes(query)
        )
    );
  }, [sortedSectors, search]);

  const positiveSectors = sortedSectors.filter(
    (sector) =>
      sector.average_constituent_return_pct !== null &&
      sector.average_constituent_return_pct > 0
  ).length;

  const bestSector = sortedSectors[0];
  const worstSector = sortedSectors[sortedSectors.length - 1];

  async function openSector(sector: Sector) {
    setDetailLoading(true);
    setError("");

    try {
      const response = await fetch(
        `${API_BASE}/sectors/${sector.sector_id}?period=${period}`,
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error(`Sector detail API returned ${response.status}`);
      }

      const result: SectorResponse = await response.json();
      const detail = result.sectors?.[0];

      if (!detail) {
        throw new Error("No sector detail was returned.");
      }

      setSelectedSector(detail);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load sector details."
      );
    } finally {
      setDetailLoading(false);
    }
  }

  function askGreedy(sector: Sector) {
    const question = [
      `Explain the NIFTY 50 sector "${sector.sector_name}" to me as a beginner.`,
      `Period: ${period}.`,
      `Average constituent price return: ${formatReturn(
        sector.average_constituent_return_pct
      )}.`,
      `Companies: ${sector.companies
        .map(
          (company) =>
            `${company.company_name} (${company.symbol}): ${formatReturn(
              company.period_return_pct
            )}`
        )
        .join("; ")}.`,
      "Explain what the numbers mean, possible reasons for the performance, risks, and what I should research next.",
      "Do not present historical performance as a prediction or personalised investment advice.",
    ].join(" ");

    router.push(`/?question=${encodeURIComponent(question)}`);
  }

  return (
    <div className="mx-auto max-w-[1500px] p-5 md:p-8">
      {/* HEADER */}

      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs text-[#a5a5a5]">
            <Compass size={14} />
            NIFTY 50 RESEARCH
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-[#eeeeee] md:text-3xl">
            Explore sectors.
          </h1>

          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#999999]">
            Understand which parts of the NIFTY 50 have performed well,
            explore their companies, and learn what the numbers mean.
          </p>
        </div>

        <button
          onClick={() => {
            setLoading(true);
            setRefreshKey((value) => value + 1);
          }}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-xl border border-[#414141] bg-[#2a2a2a] px-4 py-2.5 text-xs font-medium text-[#dddddd] transition hover:bg-[#353535] disabled:opacity-50"
        >
          <RefreshCw
            size={14}
            className={isLoading ? "animate-spin" : ""}
          />
          Refresh
        </button>
      </div>

      {/* PERIOD SELECTOR */}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-xl border border-[#383838] bg-[#1a1a1a] p-1">
          {periods.map((item) => (
            <button
              key={item}
              onClick={() => setPeriod(item)}
              className={`rounded-lg px-4 py-2 text-xs font-semibold transition ${
                period === item
                  ? "bg-[#eeeeee] text-[#171717]"
                  : "text-[#999999] hover:text-white"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        {data && (
          <p className="text-xs text-[#888888]">
            Data through{" "}
            <span className="text-[#cccccc]">
              {formatDate(data.data_as_of)}
            </span>
          </p>
        )}
      </div>

      {/* ERROR */}

      {error && (
        <div className="mb-6 flex items-start justify-between gap-3 rounded-xl border border-[#754444] bg-[#352525] p-4">
          <div>
            <p className="text-sm font-semibold text-[#f0aaaa]">
              Unable to load sector data
            </p>
            <p className="mt-1 text-xs text-[#c9a0a0]">{error}</p>
          </div>

          <button
            onClick={() => {
            setLoading(true);
            setRefreshKey((value) => value + 1);
          }}
            className="text-xs font-semibold text-white"
          >
            Retry
          </button>
        </div>
      )}

      {/* LOADING */}

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-28 animate-pulse rounded-2xl border border-[#383838] bg-[#1a1a1a]"
            />
          ))}
        </div>
      )}

      {/* DASHBOARD */}

      {!isLoading && data && !selectedSector && (
        <>
          {/* SUMMARY CARDS */}

          <div className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              label="NIFTY 50 SECTORS"
              value={String(data.sector_count)}
              detail="Sectors represented"
              icon={<Building2 size={18} />}
            />

            <SummaryCard
              label="COMPANIES"
              value={String(data.company_count)}
              detail="Latest monthly snapshot"
              icon={<Activity size={18} />}
            />

            <SummaryCard
              label="POSITIVE SECTORS"
              value={`${positiveSectors}/${data.sector_count}`}
              detail={`During the selected ${period} period`}
              icon={<TrendingUp size={18} />}
            />

            <SummaryCard
              label="DATA AS OF"
              value={formatDate(data.data_as_of)}
              detail={`Comparison from ${formatDate(
                data.comparison_target_date
              )}`}
              icon={<Compass size={18} />}
            />
          </div>

          {/* TOP AND BOTTOM PERFORMERS */}

          <div className="mb-7 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {bestSector && (
              <HighlightCard
                title="TOP PERFORMING SECTOR"
                sector={bestSector}
                positive
                onClick={() => void openSector(bestSector)}
              />
            )}

            {worstSector && (
              <HighlightCard
                title="LOWEST PERFORMING SECTOR"
                sector={worstSector}
                positive={false}
                onClick={() => void openSector(worstSector)}
              />
            )}
          </div>

          {/* SECTOR LIST HEADER */}

          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[#eeeeee]">
                Sector performance
              </h2>
              <p className="mt-1 text-xs text-[#888888]">
                Ranked by average constituent price return
              </p>
            </div>

            <div className="relative w-full sm:w-72">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#888888]"
              />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search sectors or companies..."
                className="w-full rounded-xl border border-[#414141] bg-[#1a1a1a] py-2.5 pl-9 pr-9 text-xs text-white outline-none placeholder:text-[#777777] focus:border-[#777777]"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#888888]"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          {/* SECTOR CARDS */}

          {filteredSectors.length === 0 ? (
            <div className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-10 text-center">
              <Search className="mx-auto mb-3 text-[#777777]" size={24} />
              <p className="text-sm text-[#cccccc]">No matching sectors found.</p>
              <button
                onClick={() => setSearch("")}
                className="mt-3 text-xs text-[#eeeeee] underline"
              >
                Clear search
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {filteredSectors.map((sector, index) => (
                <button
                  key={sector.sector_id}
                  onClick={() => void openSector(sector)}
                  className="group rounded-2xl border border-[#383838] bg-[#1a1a1a] p-4 text-left transition hover:border-[#606060] hover:bg-[#2c2c2c] md:p-5"
                >
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#353535] text-xs font-bold text-[#aaaaaa]">
                        {String(index + 1).padStart(2, "0")}
                      </span>

                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-[#eeeeee] group-hover:text-white">
                          {sector.sector_name}
                        </h3>
                        <p className="mt-1 text-xs text-[#888888]">
                          {sector.company_count}{" "}
                          {sector.company_count === 1 ? "company" : "companies"}
                          {" Â· "}
                          {sector.companies_with_price_data} with price data
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0 text-right">
                      <div className="text-base font-bold tabular-nums">
                        <ReturnValue
                          value={sector.average_constituent_return_pct}
                        />
                      </div>
                      <p className="mt-1 text-[10px] text-[#777777]">
                        Average return
                      </p>
                    </div>
                  </div>

                  <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[#414141]">
                    <div
                      className={`h-full rounded-full ${
                        (sector.average_constituent_return_pct ?? 0) >= 0
                          ? "bg-[#65ad86]"
                          : "bg-[#c97979]"
                      }`}
                      style={{
                        width: `${Math.min(
                          100,
                          Math.max(
                            3,
                            Math.abs(
                              sector.average_constituent_return_pct ?? 0
                            ) * 4
                          )
                        )}%`,
                      }}
                    />
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1.5">
                      {sector.companies.slice(0, 4).map((company) => (
                        <span
                          key={company.symbol}
                          className="rounded-md bg-[#353535] px-2 py-1 text-[10px] text-[#bdbdbd]"
                        >
                          {company.symbol}
                        </span>
                      ))}
                      {sector.company_count > 4 && (
                        <span className="px-1 py-1 text-[10px] text-[#888888]">
                          +{sector.company_count - 4} more
                        </span>
                      )}
                    </div>

                    <span className="flex items-center gap-1 text-[10px] text-[#999999] transition group-hover:text-white">
                      Explore
                      <ChevronRight size={13} />
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* METHODOLOGY */}

          <MethodologyNotice data={data} />
        </>
      )}

      {/* SECTOR DETAIL */}

      {!isLoading && selectedSector && data && (
        <div>
          <button
            onClick={() => setSelectedSector(null)}
            className="mb-6 flex items-center gap-2 text-xs text-[#aaaaaa] transition hover:text-white"
          >
            <ArrowLeft size={15} />
            Back to all sectors
          </button>

          <div className="mb-6 rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5 md:p-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="mb-2 text-xs text-[#999999]">
                  NIFTY 50 SECTOR DETAIL
                </p>
                <h2 className="text-2xl font-bold text-[#eeeeee]">
                  {selectedSector.sector_name}
                </h2>
                <p className="mt-2 text-xs text-[#999999]">
                  {selectedSector.company_count} companies Â· {period} performance
                </p>
              </div>

              <div className="rounded-xl bg-[#303030] p-4">
                <p className="mb-1 text-[10px] text-[#999999]">
                  AVERAGE CONSTITUENT RETURN
                </p>
                <div className="text-2xl font-bold">
                  <ReturnValue
                    value={selectedSector.average_constituent_return_pct}
                  />
                </div>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-[#303030] p-3">
                <p className="text-[10px] text-[#888888]">PRICE DATA COVERAGE</p>
                <p className="mt-1 text-lg font-semibold text-[#eeeeee]">
                  {selectedSector.data_coverage_pct.toFixed(1)}%
                </p>
              </div>

              <div className="rounded-xl bg-[#303030] p-3">
                <p className="text-[10px] text-[#888888]">COMPANIES WITH DATA</p>
                <p className="mt-1 text-lg font-semibold text-[#eeeeee]">
                  {selectedSector.companies_with_price_data}/
                  {selectedSector.company_count}
                </p>
              </div>
            </div>
          </div>

          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-[#eeeeee]">
                Companies in this sector
              </h3>
              <p className="mt-1 text-xs text-[#888888]">
                Select a company to open its profile.
              </p>
            </div>

            <button
              onClick={() => askGreedy(selectedSector)}
              className="flex items-center gap-2 rounded-xl bg-[#eeeeee] px-4 py-2.5 text-xs font-bold text-[#171717] transition hover:bg-white"
            >
              <Sparkles size={14} />
              Explore with GREEDY
            </button>
          </div>

          <div className="overflow-hidden rounded-2xl border border-[#383838] bg-[#1a1a1a]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[650px] text-left">
                <thead>
                  <tr className="border-b border-[#414141] text-[10px] uppercase tracking-wider text-[#888888]">
                    <th className="px-5 py-4 font-medium">Company</th>
                    <th className="px-4 py-4 text-right font-medium">Weight</th>
                    <th className="px-4 py-4 text-right font-medium">
                      {period} return
                    </th>
                    <th className="px-5 py-4 text-right font-medium">
                      Profile
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {selectedSector.companies.map((company) => (
                    <tr
                      key={company.symbol}
                      className="border-b border-[#383838] last:border-0 hover:bg-[#2d2d2d]"
                    >
                      <td className="px-5 py-4">
                        <p className="text-sm font-medium text-[#eeeeee]">
                          {company.company_name}
                        </p>
                        <p className="mt-1 text-[10px] text-[#888888]">
                          {company.symbol}
                        </p>
                      </td>

                      <td className="px-4 py-4 text-right text-xs text-[#bbbbbb] tabular-nums">
                        {company.weightage !== null
                          ? `${company.weightage.toFixed(2)}%`
                          : "N/A"}
                      </td>

                      <td className="px-4 py-4 text-right text-xs">
                        <ReturnValue value={company.period_return_pct} />
                      </td>

                      <td className="px-5 py-4 text-right">
                        <button
                          onClick={() =>
                            router.push(`/companies/${encodeURIComponent(company.symbol)}`)
                          }
                          className="inline-flex items-center gap-1 text-xs text-[#bbbbbb] hover:text-white"
                        >
                          View
                          <ArrowUpRight size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <MethodologyNotice data={data} />
        </div>
      )}

      {detailLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="flex items-center gap-3 rounded-xl border border-[#444444] bg-[#1a1a1a] px-5 py-4 text-sm text-[#eeeeee]">
            <RefreshCw size={16} className="animate-spin" />
            Loading sector details...
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-[10px] font-semibold tracking-wider text-[#888888]">
          {label}
        </p>
        <span className="text-[#999999]">{icon}</span>
      </div>

      <p className="text-xl font-bold text-[#eeeeee]">{value}</p>
      <p className="mt-1 text-[11px] text-[#888888]">{detail}</p>
    </div>
  );
}

function HighlightCard({
  title,
  sector,
  positive,
  onClick,
}: {
  title: string;
  sector: Sector;
  positive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-2xl border border-[#383838] bg-[#1a1a1a] p-5 text-left transition hover:border-[#606060]"
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] font-semibold tracking-wider text-[#888888]">
          {title}
        </p>
        {positive ? (
          <TrendingUp size={17} className="text-[#75c99b]" />
        ) : (
          <TrendingDown size={17} className="text-[#ed8989]" />
        )}
      </div>

      <p className="text-sm font-semibold text-[#eeeeee]">
        {sector.sector_name}
      </p>

      <div className="mt-2 text-2xl font-bold">
        <ReturnValue value={sector.average_constituent_return_pct} />
      </div>

      <p className="mt-2 text-[10px] text-[#888888]">
        {sector.company_count} constituent companies
      </p>
    </button>
  );
}

function MethodologyNotice({ data }: { data: SectorResponse }) {
  return (
    <div className="mt-7 rounded-2xl border border-[#45413a] bg-[#2b2924] p-4">
      <div className="flex items-start gap-3">
        <Activity size={16} className="mt-0.5 shrink-0 text-[#d7bd83]" />

        <div>
          <p className="text-xs font-semibold text-[#e8d6ac]">
            Understand the methodology
          </p>

          <p className="mt-2 text-xs leading-5 text-[#c5baa1]">
            Sector performance is calculated as the equal-weight average of
            available NIFTY 50 constituent price returns. It is not an official
            sector index. Prices use raw, unadjusted closing prices; dividends
            are not included.
          </p>

          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-[#a99e88]">
            <span>Price basis: {data.methodology.price_basis}</span>
            <span>Membership: Latest monthly snapshot</span>
            <span>
              Dividend adjusted:{" "}
              {data.methodology.dividend_adjusted ? "Yes" : "No"}
            </span>
            <span>Database writes: No</span>
          </div>

          <p className="mt-3 text-[10px] leading-5 text-[#a99e88]">
            Historical membership is not reconstructed for each date.
            Corporate actions are not adjusted in this endpoint. Companies
            without valid prices on both comparison dates are excluded from
            their sector average.
          </p>

          <p className="mt-2 text-[10px] text-[#a99e88]">
            Snapshot: {formatDate(data.snapshot_month)} Â· Data through:{" "}
            {formatDate(data.data_as_of)}
          </p>
        </div>
      </div>
    </div>
  );
}

