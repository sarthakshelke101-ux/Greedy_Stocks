"use client";

import { useEffect, useState } from "react";
import {
  BriefcaseBusiness,
  RefreshCw,
  TrendingUp,
  Wallet,
  AlertTriangle,
} from "lucide-react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Holding = {
  symbol: string;
  price: number;
  quantity: number;
  invested: number;
  weight: number;
  sector?: string;
};

type PeriodResult = {
  start?: string;
  end?: string;
  observations?: number;
  metrics?: {
    period_return_pct?: number;
    cagr_pct?: number;
    annualized_volatility_pct?: number;
    maximum_drawdown_pct?: number;
    sharpe_ratio?: number;
  };
  benchmark?: {
    portfolio_return_pct?: number;
    benchmark_return_pct?: number;
    excess_return_pct?: number;
  };
};

type PortfolioResult = {
  status: string;
  selection_method: string;
  portfolio: {
    capital: number;
    invested: number;
    cash_remaining: number;
    stock_count: number;
    holdings: Holding[];
  };
  selection_log: {
    step: number;
    symbol: string;
    portfolio_sharpe: number;
    marginal_sharpe_change: number | null;
  }[];
  training: {
    start: string;
    end: string;
    observations: number;
    selection_sharpe: number;
  };
  validation: PeriodResult;
  test: PeriodResult;
  data_limitations: {
    historical_membership_survivorship_bias?: boolean;
    dividend_adjusted?: boolean;
    corporate_action_coverage?: string;
    validation_test_missing_prices_filled?: boolean;
  };
  assumptions: {
    selection_method: string;
    daily_rebalancing: boolean;
    selection_uses_training_data_only: boolean;
    globally_optimal: boolean;
    user_selected_symbols?: string[];
    greedy_selected_symbols?: string[];
  };
};

const money = (value?: number) =>
  typeof value === "number"
    ? value.toLocaleString("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      })
    : "?";

const pct = (value?: number) =>
  typeof value === "number" ? `${value.toFixed(2)}%` : "?";

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
    <div className="rounded-xl border border-[#343434] bg-[#000000] p-4">
      <p className="text-xs text-[#a3a3a3]">{label}</p>
      <p className="mt-2 text-xl font-semibold text-white">{value}</p>
      {detail && <p className="mt-1 text-xs text-[#888]">{detail}</p>}
    </div>
  );
}

function Performance({
  title,
  period,
}: {
  title: string;
  period: PeriodResult;
}) {
  const m = period.metrics;
  const b = period.benchmark;

  return (
    <section className="rounded-2xl border border-[#343434] bg-[#171717] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <span className="text-xs text-[#999]">
          {period.start ?? "?"} to {period.end ?? "?"}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Metric label="Period return" value={pct(m?.period_return_pct)} />
        <Metric label="CAGR" value={pct(m?.cagr_pct)} />
        <Metric label="Sharpe ratio" value={m?.sharpe_ratio?.toFixed(3) ?? "?"} />
        <Metric
          label="Annualized volatility"
          value={pct(m?.annualized_volatility_pct)}
        />
        <Metric
          label="Maximum drawdown"
          value={pct(m?.maximum_drawdown_pct)}
        />
        <Metric
          label="NIFTY 50 return"
          value={pct(b?.benchmark_return_pct)}
          detail={`Excess return: ${pct(b?.excess_return_pct)}`}
        />
      </div>
    </section>
  );
}

export default function PortfolioBuilder({ initialSelectedStock = "" }: { initialSelectedStock?: string }) {
  const [capital, setCapital] = useState("100000");
  const [stockCount, setStockCount] = useState("5");
  const [maxPerSector, setMaxPerSector] = useState("3");
  const [trainingYears, setTrainingYears] = useState("10");
  const [riskFreeRate, setRiskFreeRate] = useState("0");
  const [result, setResult] = useState<PortfolioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [addedStocks, setAddedStocks] = useState<string[]>([]);

  useEffect(() => {
    const key = "greedy-stocks-selected";
    let saved: string[] = [];

    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      if (Array.isArray(parsed)) {
        saved = parsed.filter(
          (item): item is string => typeof item === "string"
        ).map((item) => item.toUpperCase());
      }
    } catch {
      saved = [];
    }

    const merged = Array.from(new Set([
      ...saved,
      ...(initialSelectedStock ? [initialSelectedStock.toUpperCase()] : []),
    ]));

    setAddedStocks(merged);
    localStorage.setItem(key, JSON.stringify(merged));
  }, [initialSelectedStock]);

  function removeAddedStock(symbol: string) {
    const updated = addedStocks.filter((item) => item !== symbol);
    setAddedStocks(updated);
    localStorage.setItem("greedy-stocks-selected", JSON.stringify(updated));
  }

  async function generatePortfolio(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/portfolio/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          capital: Number(capital),
          stock_count: Number(stockCount),
          training_years: Number(trainingYears),
          max_per_sector: Number(maxPerSector),
          risk_free_rate: Number(riskFreeRate) / 100,
          selected_symbols: addedStocks,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail ?? "Portfolio generation failed.")
        );
      }

      setResult(data as PortfolioResult);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not connect to GREEDY STOCKS API."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-[1500px] space-y-6 p-5 md:p-8">
      <header>
        <div className="mb-2 flex items-center gap-2 text-xs text-[#aaa]">
          <BriefcaseBusiness size={15} />
          GREEDY V2 PORTFOLIO ENGINE
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-white">
          Portfolio Builder
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[#aaa]">
          Generate a whole-share portfolio using sequential greedy Sharpe
          selection and evaluate it against NIFTY 50.
        </p>
      </header>

      {addedStocks.length > 0 && (
        <section className="rounded-2xl border border-cyan-400/30 bg-cyan-400/5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
              Your selected stocks
            </p>
            <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-200">
              {addedStocks.length} {addedStocks.length === 1 ? "stock" : "stocks"} saved
            </span>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {addedStocks.map((symbol) => (
              <span key={symbol} className="inline-flex items-center gap-3 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 font-semibold text-cyan-200">
                {symbol}
                <button
                  type="button"
                  onClick={() => removeAddedStock(symbol)}
                  aria-label={`Remove ${symbol}`}
                  className="text-lg leading-none text-cyan-200/70 transition hover:text-red-300"
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <p className="mt-3 text-xs leading-5 text-[#aaa]">
            Your research list is saved in this browser and survives navigation and refreshes.
            These stocks stay in your portfolio. Greedy V2 selects the remaining slots.
          </p>
        </section>
      )}
      <form
        onSubmit={generatePortfolio}
        className="grid gap-4 rounded-2xl border border-[#303030] bg-[#171717] p-5 md:grid-cols-2 xl:grid-cols-5"
      >
        <label className="text-sm text-[#bbb]">
          Investment capital (INR)
          <input
            required
            type="number"
            min="1"
            max="100000000000"
            step="0.01"
            value={capital}
            onChange={(e) => setCapital(e.target.value)}
            className="mt-2 w-full rounded-lg border border-[#444] bg-[#171717] px-3 py-3 text-white outline-none focus:border-[#888]"
          />
        </label>

        <label className="text-sm text-[#bbb]">
          Number of stocks
          <select
            value={stockCount}
            onChange={(e) => setStockCount(e.target.value)}
            className="mt-2 w-full rounded-lg border border-[#444] bg-[#171717] px-3 py-3 text-white"
          >
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>{n} stocks</option>
            ))}
          </select>
        </label>

        <label className="text-sm text-[#bbb]">
          Maximum stocks per sector
          <select
            value={maxPerSector}
            onChange={(e) => setMaxPerSector(e.target.value)}
            className="mt-2 w-full rounded-lg border border-[#444] bg-[#171717] px-3 py-3 text-white"
          >
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <label className="text-sm text-[#bbb]">
          Training history
          <select
            value={trainingYears}
            onChange={(e) => setTrainingYears(e.target.value)}
            className="mt-2 w-full rounded-lg border border-[#444] bg-[#171717] px-3 py-3 text-white"
          >
            {[1, 2, 3, 5, 7, 10].map((n) => (
              <option key={n} value={n}>{n} years</option>
            ))}
          </select>
        </label>

        <label className="text-sm text-[#bbb]">
          Annual risk-free rate (%)
          <input
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={riskFreeRate}
            onChange={(e) => setRiskFreeRate(e.target.value)}
            className="mt-2 w-full rounded-lg border border-[#444] bg-[#171717] px-3 py-3 text-white"
          />
        </label>

        <div className="flex items-end md:col-span-2 xl:col-span-5">
          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 font-semibold text-black transition hover:bg-[#ddd] disabled:cursor-not-allowed disabled:opacity-50 md:w-auto"
          >
            {loading ? (
              <RefreshCw size={17} className="animate-spin" />
            ) : (
              <TrendingUp size={17} />
            )}
            {loading ? "Generating portfolio..." : "Generate Greedy V2 Portfolio"}
          </button>
        </div>
      </form>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!result && !loading && !error && (
        <div className="rounded-2xl border border-dashed border-[#444] p-10 text-center">
          <Wallet size={30} className="mx-auto text-[#888]" />
          <h3 className="mt-3 font-semibold text-white">
            Your portfolio will appear here
          </h3>
          <p className="mt-2 text-sm text-[#999]">
            Choose stocks you want to keep. Greedy V2 fills the remaining slots.
          </p>
        </div>
      )}

      {result && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Starting capital" value={money(result.portfolio.capital)} />
            <Metric label="Amount invested" value={money(result.portfolio.invested)} />
            <Metric label="Cash remaining" value={money(result.portfolio.cash_remaining)} />
            <Metric
              label="Selected stocks"
              value={String(result.portfolio.stock_count)}
              detail="Whole-share allocation"
            />
          </section>

          <section className="overflow-hidden rounded-2xl border border-[#303030] bg-[#171717]">
            <div className="border-b border-[#303030] p-5">
              <h2 className="text-lg font-semibold text-white">Your holdings</h2>
              <p className="mt-1 text-xs text-[#999]">
                Latest available raw closing prices; quantities are whole shares.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[650px] text-left text-sm">
                <thead className="bg-[#292929] text-xs text-[#aaa]">
                  <tr>
                    <th className="px-5 py-3">Stock</th>
                    <th className="px-5 py-3">Sector</th>
                    <th className="px-5 py-3 text-right">Price</th>
                    <th className="px-5 py-3 text-right">Quantity</th>
                    <th className="px-5 py-3 text-right">Investment</th>
                    <th className="px-5 py-3 text-right">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {result.portfolio.holdings.map((holding) => (
                    <tr key={holding.symbol} className="border-t border-[#353535] text-[#eee]">
                      <td className="px-5 py-4 font-semibold">{holding.symbol}</td>
                      <td className="px-5 py-4 text-[#aaa]">{holding.sector ?? "?"}</td>
                      <td className="px-5 py-4 text-right">{money(holding.price)}</td>
                      <td className="px-5 py-4 text-right">{holding.quantity}</td>
                      <td className="px-5 py-4 text-right">{money(holding.invested)}</td>
                      <td className="px-5 py-4 text-right">{(holding.weight * 100).toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-2xl border border-[#303030] bg-[#171717] p-5">
            <h2 className="text-lg font-semibold text-white">Greedy selection journey</h2>
            <p className="mt-1 text-xs text-[#999]">
              Training period: {result.training.start} to {result.training.end}
              {" ? "}{result.training.observations.toLocaleString("en-IN")} observations
              {" ? "}Selection Sharpe: {result.training.selection_sharpe.toFixed(3)}
            </p>
            <div className="mt-4 space-y-3">
              {(result.assumptions.user_selected_symbols ?? []).map((symbol, index) => (
                <div key={`user-${symbol}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-cyan-900/60 bg-[#092024] p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-[#888]">#{index + 1}</span>
                    <span className="font-semibold text-white">{symbol}</span>
                    <span className="rounded-full bg-cyan-950 px-2 py-1 text-xs font-medium text-cyan-300">
                      USER-SELECTED
                    </span>
                  </div>
                </div>
              ))}
              {result.selection_log.map((step) => (
                <div key={step.step} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[#292929] p-3 text-sm">
                  <div>
                    <span className="mr-3 text-[#888]">#{step.step}</span>
                    <span className="font-semibold text-white">{step.symbol}</span>
                    <span className="ml-2 rounded-full bg-[#303030] px-2 py-1 text-xs text-[#bbb]">
                      GREEDY V2
                    </span>
                  </div>
                  <div className="text-right text-[#bbb]">
                    Sharpe {step.portfolio_sharpe.toFixed(3)}
                    {step.marginal_sharpe_change !== null && (
                      <span className={step.marginal_sharpe_change >= 0 ? "ml-3 text-green-400" : "ml-3 text-red-400"}>
                        {step.marginal_sharpe_change >= 0 ? "+" : ""}
                        {step.marginal_sharpe_change.toFixed(3)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-4 xl:grid-cols-2">
            <Performance title="Validation performance" period={result.validation} />
            <Performance title="Out-of-sample test performance" period={result.test} />
          </div>

          <section className="rounded-2xl border border-[#303030] bg-[#171717] p-5">
            <h2 className="text-lg font-semibold text-white">Methodology and data limitations</h2>
            <ul className="mt-3 grid gap-2 text-sm text-[#bbb] md:grid-cols-2">
              <li>? Selection method: {result.assumptions.selection_method}</li>
              <li>? Daily rebalancing: {result.assumptions.daily_rebalancing ? "Yes" : "No"}</li>
              <li>? Selection uses training data only: {result.assumptions.selection_uses_training_data_only ? "Yes" : "No"}</li>
              <li>? Globally optimal: {result.assumptions.globally_optimal ? "Yes" : "No"}</li>
              <li>? Dividend adjusted: {result.data_limitations.dividend_adjusted ? "Yes" : "No"}</li>
              <li>? Corporate-action coverage: {result.data_limitations.corporate_action_coverage ?? "Not specified"}</li>
              <li>? Survivorship bias: {result.data_limitations.historical_membership_survivorship_bias ? "Present" : "Not flagged"}</li>
              <li>? Missing evaluation prices filled: {result.data_limitations.validation_test_missing_prices_filled ? "Yes" : "No"}</li>
            </ul>
            <p className="mt-4 border-t border-[#303030] pt-4 text-xs leading-6 text-[#999]">
              Historical validation and test metrics represent a daily-rebalanced,
              equal-weight research portfolio. They are not the realized buy-and-hold
              performance of the whole-share holdings shown above. Historical results
              do not guarantee future returns. For educational research only, not
              investment advice.
            </p>
          </section>
        </>
      )}
    </main>
  );
}
