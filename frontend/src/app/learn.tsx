"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BookOpen, CheckCircle2, ChevronDown, ChevronRight,
  CircleHelp, GraduationCap, Lock, Play, RotateCcw,
  Trophy
} from "lucide-react";

type Lesson = {
  id: string;
  title: string;
  explanation: string;
  example: string;
  question: string;
  options: string[];
  answer: number;
  takeaway: string;
};

type Phase = {
  id: number;
  title: string;
  description: string;
  lessons: Lesson[];
};

const phases: Phase[] = [
  {
    id: 1,
    title: "Stock Market Fundamentals",
    description: "Start from zero. Understand shares, stock markets and how investing works.",
    lessons: [
      {
        id: "p1-1", title: "What is the stock market?",
        explanation: "The stock market is a place where investors buy and sell ownership shares in publicly listed companies. It helps companies raise money and gives investors a way to participate in their growth.",
        example: "Imagine a company needs money to expand its business. It can offer ownership shares to the public. Investors who buy those shares become part-owners.",
        question: "What is the main purpose of a stock market?",
        options: ["Only to lend money to banks", "To enable buying and selling company shares", "To guarantee investment profits", "To set government taxes"],
        answer: 1, takeaway: "A stock market connects companies seeking capital with investors seeking ownership."
      },
      {
        id: "p1-2", title: "How does the stock market work?",
        explanation: "Buyers and sellers place orders through brokers. Exchanges match compatible orders based on price and time priority. Transactions are then cleared and settled through the market infrastructure.",
        example: "If someone offers to sell a share at ?100 and a buyer agrees to pay ?100, their orders can match.",
        question: "Who matches compatible buy and sell orders?",
        options: ["The company CEO", "The stock exchange trading system", "The income tax department", "The investor's employer"],
        answer: 1, takeaway: "Exchanges provide an organised system for trading securities."
      },
      {
        id: "p1-3", title: "What is a stock?",
        explanation: "A stock represents ownership in a company. When you own stock, you own a portion of that business, subject to the rights attached to the security.",
        example: "Owning shares of a listed Indian company means holding a small ownership interest in that company.",
        question: "What does owning stock generally represent?",
        options: ["A loan to the government", "Ownership in a company", "A guaranteed bank deposit", "A fixed monthly salary"],
        answer: 1, takeaway: "Stock ownership is an ownership claim, not a guaranteed return."
      },
      {
        id: "p1-4", title: "What is a share?",
        explanation: "A share is an individual unit of ownership in a company. A company's equity is divided into shares.",
        example: "If a company has 1,000 shares and you own 10, you hold 1% of those shares.",
        question: "If you own 10 out of 1,000 equal shares, what proportion do you own?",
        options: ["0.1%", "1%", "10%", "50%"],
        answer: 1, takeaway: "A share is one unit of a company's ownership."
      },
      {
        id: "p1-5", title: "Why do companies sell shares?",
        explanation: "Companies may issue shares to raise capital for expansion, research, hiring, debt reduction or other business purposes. Existing shareholders may also sell shares in the market.",
        example: "A company might raise funds through an IPO to build a new manufacturing facility.",
        question: "Why might a company issue new shares?",
        options: ["To raise capital", "To guarantee its share price", "To eliminate all business risk", "To promise dividends"],
        answer: 0, takeaway: "Equity can help a company raise funds, but it also distributes ownership."
      },
      {
        id: "p1-6", title: "Why do people buy stocks?",
        explanation: "Investors may buy shares to participate in a company's potential growth, receive dividends when declared, or diversify their investments. Returns are uncertain.",
        example: "An investor may buy shares because they believe the business can grow over several years.",
        question: "Which statement is correct?",
        options: ["Stocks always rise", "Stocks guarantee dividends", "Investors may participate in business growth but face risk", "Every stock pays interest"],
        answer: 2, takeaway: "Potential reward comes with uncertainty and risk."
      },
      {
        id: "p1-7", title: "How do people make money from stocks?",
        explanation: "Two common sources are capital gains when a share is sold for more than its purchase cost, and dividends when a company distributes profits. Neither is guaranteed.",
        example: "Buying at ?100 and selling at ?120 creates a ?20 price gain per share before costs and taxes.",
        question: "What is a capital gain?",
        options: ["A rise in the value realised on sale", "A guaranteed dividend", "A brokerage charge", "A stock exchange holiday"],
        answer: 0, takeaway: "Returns can come from price appreciation and dividends."
      },
      {
        id: "p1-8", title: "Can I lose money in the stock market?",
        explanation: "Yes. A share price can fall, a company can perform poorly, and an investor may sell below their purchase price. Some companies can even fail.",
        example: "Buying at ?100 and selling at ?80 means a ?20 loss per share before costs.",
        question: "What happens if you buy at ?100 and sell at ?80?",
        options: ["?20 profit", "?20 loss", "No change", "Guaranteed dividend"],
        answer: 1, takeaway: "Never assume stock-market returns are guaranteed."
      },
      {
        id: "p1-9", title: "Who decides stock prices?",
        explanation: "Market prices emerge from the interaction of buy and sell orders. Demand, supply, expectations and available information influence the price.",
        example: "If many investors compete to buy at higher prices while few are willing to sell, the traded price may rise.",
        question: "What primarily determines a traded stock price?",
        options: ["A fixed government price", "The interaction of buyers and sellers", "The company's office rent", "The number of employees alone"],
        answer: 1, takeaway: "Prices emerge through market supply and demand."
      },
      {
        id: "p1-10", title: "Why do stock prices change every day?",
        explanation: "Prices change as investors react to company results, economic data, interest rates, news, expectations and changes in demand or supply.",
        example: "A company reporting stronger-than-expected results may attract more buyers, although the price reaction is never certain.",
        question: "Which can influence daily stock prices?",
        options: ["Company results", "Economic news", "Investor expectations", "All of these"],
        answer: 3, takeaway: "Prices continuously reflect changing expectations and trading activity."
      },
      {
        id: "p1-11", title: "What happens when I purchase a share?",
        explanation: "Your broker routes your order to an exchange. Once matched, the trade is cleared and settled. The purchased security is credited to your demat account under the applicable settlement process.",
        example: "After a successful delivery purchase and settlement, the shares appear in your demat holdings.",
        question: "Where are your dematerialised shares held?",
        options: ["Savings account", "Demat account", "Email inbox", "Credit card"],
        answer: 1, takeaway: "A demat account holds securities electronically."
      },
      {
        id: "p1-12", title: "Can a company run out of shares?",
        explanation: "The number of issued shares is finite at a given time, but shares can be traded repeatedly between investors. A company can also issue additional shares through permitted corporate actions.",
        example: "The same share can be bought and sold many times without the company creating a new share each time.",
        question: "Does every stock-market purchase require a newly issued share?",
        options: ["Yes", "No, existing shares can change owners", "Only on Mondays", "Only during IPOs"],
        answer: 1, takeaway: "Most exchange trading transfers existing shares between investors."
      },
      {
        id: "p1-13", title: "Investing vs trading",
        explanation: "Investing generally focuses on ownership and longer-term goals. Trading generally seeks to benefit from shorter-term price movements. Both involve risk and require informed decisions.",
        example: "A person holding a company's shares for years may be investing; someone buying and selling within days may be trading.",
        question: "Which activity usually focuses on a longer time horizon?",
        options: ["Investing", "Intraday trading", "Scalping", "Neither"],
        answer: 0, takeaway: "The main distinction is the objective and time horizon."
      },
      {
        id: "p1-14", title: "Is the stock market gambling?",
        explanation: "Investing is not automatically gambling. Research, valuation, diversification and risk management can inform decisions. However, speculation without understanding risk can resemble gambling-like behaviour.",
        example: "Studying a company's finances is different from buying a random stock solely because its price is moving.",
        question: "What helps distinguish informed investing from blind speculation?",
        options: ["Research and risk management", "Rumours alone", "Guaranteed returns", "Ignoring losses"],
        answer: 0, takeaway: "Knowledge and disciplined risk management matter."
      },
      {
        id: "p1-15", title: "Can I learn without investing money?",
        explanation: "Absolutely. You can study market concepts, examine historical prices, use paper portfolios and practise calculations without placing real orders.",
        example: "A virtual portfolio can help you observe how hypothetical investments behave.",
        question: "What is a paper portfolio?",
        options: ["A physical share certificate", "A simulated portfolio without real-money trades", "A bank loan", "An IPO application"],
        answer: 1, takeaway: "Learn and practise before considering real-money investing."
      }
    ]
  },
  {
    id: 2,
    title: "Understanding NIFTY 50",
    description: "Understand India's flagship index, its companies, sectors and behaviour.",
    lessons: [
      {
        id: "p2-1", title: "What exactly is NIFTY 50?",
        explanation: "NIFTY 50 is a benchmark stock-market index designed to represent the performance of a diversified group of 50 large, liquid companies listed on the National Stock Exchange of India.",
        example: "When people say NIFTY rose, they are referring to a change in the index level, not every individual stock rising.",
        question: "What does NIFTY 50 represent?",
        options: ["All Indian companies", "A benchmark index of 50 selected companies", "Only government bonds", "A mutual fund"],
        answer: 1, takeaway: "An index summarises the movement of a selected group of securities."
      },
      {
        id: "p2-2", title: "Why does NIFTY have 50 companies?",
        explanation: "The index uses a defined set of 50 constituents to represent a broad cross-section of large and liquid listed companies. The number is part of the index's design.",
        example: "The index combines companies from multiple sectors rather than representing one business alone.",
        question: "Does NIFTY 50 contain every listed Indian company?",
        options: ["Yes", "No", "Only small companies", "Only banks"],
        answer: 1, takeaway: "NIFTY 50 is a selected benchmark, not the entire market."
      },
      {
        id: "p2-3", title: "How is NIFTY 50 calculated?",
        explanation: "NIFTY 50 uses free-float market-capitalisation weighting. Companies with larger eligible free-float market capitalisations generally have greater influence on the index.",
        example: "A constituent with a larger index weight can affect the index more than a smaller-weight constituent for the same percentage price move.",
        question: "What weighting approach does NIFTY 50 use?",
        options: ["Equal weighting", "Free-float market-capitalisation weighting", "Random weighting", "Alphabetical weighting"],
        answer: 1, takeaway: "Index weightage determines how much each constituent influences the index."
      },
      {
        id: "p2-4", title: "What determines a company's place in NIFTY 50?",
        explanation: "Index selection follows published eligibility and selection rules, including liquidity, free-float market capitalisation and other index methodology requirements.",
        example: "A large company does not automatically enter the index merely because its market value is high.",
        question: "Are NIFTY 50 additions decided randomly?",
        options: ["Yes", "No, published methodology is followed", "By social-media polls", "By individual investors"],
        answer: 1, takeaway: "Index inclusion follows formal methodology."
      },
      {
        id: "p2-5", title: "How frequently does composition change?",
        explanation: "NIFTY 50 constituents are reviewed periodically under the index methodology. Changes can also arise from specified corporate events.",
        example: "A company may be replaced when it no longer satisfies relevant selection requirements.",
        question: "Can NIFTY 50 constituents change over time?",
        options: ["Never", "Yes, through index reviews and specified events", "Every trading day", "Only when investors vote"],
        answer: 1, takeaway: "The index evolves as companies and eligibility change."
      },
      {
        id: "p2-6", title: "Who manages the NIFTY indices?",
        explanation: "NSE Indices Limited is responsible for managing and maintaining NIFTY indices under their published methodologies.",
        example: "Index methodology documents describe eligibility, calculation and review rules.",
        question: "Which organisation manages NIFTY indices?",
        options: ["RBI", "NSE Indices Limited", "Every listed company", "A retail broker"],
        answer: 1, takeaway: "Index providers maintain the rules and calculation of their indices."
      },
      {
        id: "p2-7", title: "What is index weightage?",
        explanation: "Weightage is the percentage contribution assigned to a constituent in an index calculation. Larger weights generally mean greater influence on index movement.",
        example: "A 10% weight means that the constituent represents 10% of the index's weighted market-capitalisation calculation at that point.",
        question: "What does a larger index weight usually mean?",
        options: ["More influence on index movement", "Guaranteed higher returns", "Lower risk", "A fixed share price"],
        answer: 0, takeaway: "Weightage measures influence, not investment quality."
      },
      {
        id: "p2-8", title: "Why do some companies have higher weightage?",
        explanation: "Free-float market capitalisation is a key driver. It considers market value adjusted for shares available for public trading under the methodology.",
        example: "A company with a larger eligible free-float market value may receive a higher weight.",
        question: "Which factor is central to NIFTY 50 weighting?",
        options: ["Office size", "Free-float market capitalisation", "Number of advertisements", "CEO age"],
        answer: 1, takeaway: "Index weights are based on the index methodology, not popularity alone."
      },
      {
        id: "p2-9", title: "Can NIFTY rise when most stocks fall?",
        explanation: "Yes. A few heavily weighted constituents can rise enough to offset declines in many smaller-weight constituents.",
        example: "If the largest companies rise strongly, the index may gain even while more individual stocks decline.",
        question: "Why can an index rise while most constituents fall?",
        options: ["All stocks have equal weight", "Heavily weighted stocks can dominate", "The index ignores prices", "Trading is suspended"],
        answer: 1, takeaway: "Breadth and index direction are not always the same."
      },
      {
        id: "p2-10", title: "Does NIFTY 50 represent the entire market?",
        explanation: "No. It represents a selected group of large, liquid companies. Smaller companies and many other listed securities are outside the index.",
        example: "A small-cap stock can rise sharply without having any direct weight in NIFTY 50.",
        question: "Does NIFTY 50 cover every listed stock?",
        options: ["Yes", "No", "Only IPOs", "Only public-sector companies"],
        answer: 1, takeaway: "Always understand what an index includes and excludes."
      }
    ]
  },
  {
    id: 3,
    title: "Understanding Stock Performance",
    description: "Learn prices, percentage changes, returns and how to interpret performance.",
    lessons: [
      {
        id: "p3-1", title: "What does a 5% return mean?",
        explanation: "A 5% return means the investment's value increased by 5% relative to the starting amount, ignoring costs, taxes and cash flows.",
        example: "A ?1,000 investment growing by 5% becomes ?1,050. The gain is ?50.",
        question: "What is a 5% gain on ?1,000?",
        options: ["?5", "?50", "?500", "?1,500"],
        answer: 1, takeaway: "Percentage return expresses change relative to the starting value."
      },
      {
        id: "p3-2", title: "What happens when a stock falls by 10%?",
        explanation: "A 10% fall reduces the current value by one-tenth of its starting value for that period.",
        example: "A share priced at ?500 falling by 10% becomes ?450. The decline is ?50.",
        question: "What is ?500 after a 10% fall?",
        options: ["?550", "?490", "?450", "?400"],
        answer: 2, takeaway: "A percentage decline is calculated from the value before the fall."
      },
      {
        id: "p3-3", title: "Profit, loss and capital",
        explanation: "Capital is the money invested. Profit is a positive difference between proceeds and costs. Loss is a negative difference. Realised and unrealised results are different.",
        example: "Invest ?2,000 and later sell for ?2,300: the price gain is ?300 before charges and taxes.",
        question: "What is capital in investing?",
        options: ["Money committed to an investment", "A stock exchange", "A dividend", "A trading holiday"],
        answer: 0, takeaway: "Know your starting capital before evaluating returns."
      },
      {
        id: "p3-4", title: "What is compounding?",
        explanation: "Compounding occurs when returns remain invested and future returns are earned on both the original capital and accumulated gains. Actual returns vary and are not guaranteed.",
        example: "If ?1,000 grows by 10%, it becomes ?1,100. A further 10% gain makes it ?1,210.",
        question: "What is the value after two successive 10% gains on ?1,000?",
        options: ["?1,200", "?1,210", "?1,100", "?1,020"],
        answer: 1, takeaway: "Compounding builds on the changing investment value."
      },
      {
        id: "p3-5", title: "Daily return and annual return",
        explanation: "Daily return measures a change over one day. Annual return measures performance over a year or an annualised period. Annualised returns should not be confused with a simple one-year gain.",
        example: "A share rising from ?100 to ?101 has a one-day price return of 1%.",
        question: "A daily return measures performance over what period?",
        options: ["One trading day", "Ten years", "One financial quarter only", "An IPO period"],
        answer: 0, takeaway: "Always check the time period behind a return figure."
      },
      {
        id: "p3-6", title: "Percentage change and stock prices",
        explanation: "Percentage change compares the difference between two values with the starting value. A ?100 stock is not automatically cheaper than a ?1,000 stock; valuation depends on business fundamentals and shares outstanding, among other factors.",
        example: "A move from ?100 to ?110 is 10%. A move from ?1,000 to ?1,050 is 5%.",
        question: "Which stock is necessarily cheaper: ?100 or ?1,000?",
        options: ["?100 stock always", "?1,000 stock always", "Neither can be judged by price alone", "Both have identical valuation"],
        answer: 2, takeaway: "Share price alone does not tell you whether a company is undervalued."
      }
    ]
  },
  {
    id: 4,
    title: "Company Analysis",
    description: "Understand what businesses do, how sectors differ and what to research.",
    lessons: [
      {
        id: "p4-1", title: "What does a company actually do?",
        explanation: "Company analysis begins by understanding its products, services, customers, suppliers and how it earns revenue.",
        example: "A bank earns income through lending and other financial services, while an IT services company earns revenue by providing technology services.",
        question: "What is a good first step in company analysis?",
        options: ["Understand its business model", "Buy immediately", "Ignore its customers", "Look only at its share price"],
        answer: 0, takeaway: "Understand the business before interpreting its stock."
      },
      {
        id: "p4-2", title: "Understanding revenue and profit",
        explanation: "Revenue is income earned from business operations. Profit is what remains after relevant expenses are deducted. A company can grow revenue while its profit falls.",
        example: "A business earns ?100 crore revenue and incurs ?90 crore expenses. Its simplified profit is ?10 crore.",
        question: "What is profit in this simplified example?",
        options: ["?100 crore", "?90 crore", "?10 crore", "?190 crore"],
        answer: 2, takeaway: "Revenue and profit are not the same thing."
      },
      {
        id: "p4-3", title: "Understanding business sectors",
        explanation: "Sectors group companies with related economic activities. Common examples include banking, information technology, automobiles, pharmaceuticals and energy.",
        example: "Banks and automobile manufacturers operate in different sectors and face different business drivers.",
        question: "Which sector does a bank belong to?",
        options: ["Banking and financial services", "Automobiles", "Pharmaceuticals", "Metals"],
        answer: 0, takeaway: "Sector context helps you compare similar businesses."
      },
      {
        id: "p4-4", title: "What should you research about a company?",
        explanation: "Useful research areas include business model, revenue and profit trends, debt, cash flow, management, competition, valuation and risks.",
        example: "Two companies can have similar revenue but very different debt levels and profitability.",
        question: "Which is useful in company research?",
        options: ["Cash flow", "Debt", "Competition", "All of these"],
        answer: 3, takeaway: "Company analysis uses several sources of evidence, not one number."
      },
      {
        id: "p4-5", title: "Reading company financials",
        explanation: "The income statement, balance sheet and cash-flow statement provide complementary views of financial performance, financial position and cash generation.",
        example: "A company may report accounting profit but still have weak operating cash flow.",
        question: "Which statement focuses on cash generated and used?",
        options: ["Cash-flow statement", "Only the share-price chart", "Index methodology", "Trading calendar"],
        answer: 0, takeaway: "Read financial statements together rather than in isolation."
      }
    ]
  },
  {
    id: 5,
    title: "Risk and Portfolio Construction",
    description: "Understand uncertainty, diversification and how portfolios are evaluated.",
    lessons: [
      {
        id: "p5-1", title: "What is investment risk?",
        explanation: "Investment risk is the possibility that actual outcomes differ from expectations, including the possibility of losing capital.",
        example: "A company's business may weaken unexpectedly, causing its stock price to fall.",
        question: "Does every investment have some form of risk?",
        options: ["Yes", "No investment has risk", "Only expensive stocks", "Only foreign stocks"],
        answer: 0, takeaway: "Risk cannot be eliminated, but it can be understood and managed."
      },
      {
        id: "p5-2", title: "What is volatility?",
        explanation: "Volatility describes how much returns fluctuate over time. It is commonly measured using the standard deviation of returns.",
        example: "A stock whose daily returns swing widely is generally more volatile than one whose returns change modestly.",
        question: "What does volatility measure?",
        options: ["Return fluctuations", "Company employee count", "Dividend tax", "Number of exchanges"],
        answer: 0, takeaway: "Volatility is one measure of risk, not a complete description of risk."
      },
      {
        id: "p5-3", title: "Market crashes and corrections",
        explanation: "A correction is commonly used for a decline of around 10% from a recent peak. A crash generally refers to a much sharper and more disruptive decline. Definitions vary.",
        example: "A broad index falling sharply over a short period may be described as a market crash.",
        question: "Which term generally describes a sudden, severe market decline?",
        options: ["Market crash", "Dividend", "Compounding", "Index rebalancing"],
        answer: 0, takeaway: "Market declines differ in scale, speed and cause."
      },
      {
        id: "p5-4", title: "What is a 52-week high and low?",
        explanation: "A 52-week high is the highest recorded price over the preceding 52 weeks; a 52-week low is the lowest. These are reference points, not predictions.",
        example: "A stock trading at ?900 with a 52-week high of ?1,000 is not automatically undervalued.",
        question: "Does a 52-week low guarantee a stock is cheap?",
        options: ["Yes", "No", "Only for banks", "Only during IPOs"],
        answer: 1, takeaway: "Historical price extremes do not replace valuation analysis."
      },
      {
        id: "p5-5", title: "What is diversification?",
        explanation: "Diversification spreads investments across different securities, sectors or asset types to reduce dependence on a single holding. It does not guarantee a profit or prevent all losses.",
        example: "Holding companies from banking, IT and healthcare can reduce concentration in one sector.",
        question: "What is a key purpose of diversification?",
        options: ["Reduce concentration risk", "Guarantee profits", "Remove all market risk", "Predict tomorrow's price"],
        answer: 0, takeaway: "Diversification can help manage company-specific and sector concentration."
      },
      {
        id: "p5-6", title: "Understanding drawdown",
        explanation: "Drawdown measures the decline from a previous portfolio peak to a later low. Maximum drawdown is the largest such decline over a selected period.",
        example: "A portfolio falling from ?1,00,000 to ?80,000 experiences a 20% drawdown from that peak.",
        question: "What is the drawdown from ?1,00,000 to ?80,000?",
        options: ["10%", "20%", "25%", "80%"],
        answer: 1, takeaway: "Drawdown helps describe the depth of historical losses."
      },
      {
        id: "p5-7", title: "What is the Sharpe ratio?",
        explanation: "The Sharpe ratio is an established measure of excess return per unit of volatility. It is calculated using portfolio return above a risk-free rate divided by the standard deviation of returns. It is not a guarantee of future performance.",
        example: "A higher Sharpe ratio can indicate more historical excess return per unit of measured volatility, when periods and assumptions are comparable.",
        question: "What does the Sharpe ratio relate?",
        options: ["Excess return to volatility", "Revenue to employees", "Price to share count", "Dividend to tax rate"],
        answer: 0, takeaway: "Sharpe is a useful comparison metric, but it does not capture every kind of risk."
      },
      {
        id: "p5-8", title: "Understanding portfolio weights",
        explanation: "A portfolio weight is the proportion of portfolio value allocated to a particular holding. Weights help explain concentration and diversification.",
        example: "If ?20,000 of a ?1,00,000 portfolio is in one stock, its weight is 20%.",
        question: "What is the weight of ?20,000 in a ?1,00,000 portfolio?",
        options: ["2%", "10%", "20%", "50%"],
        answer: 2, takeaway: "Portfolio weights show where the capital is allocated."
      }
    ]
  }
];

const STORAGE_KEY = "greedy-learn-progress-v1";

export default function LearnPage() {
  const [completed, setCompleted] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<number>(1);
  const [activeLesson, setActiveLesson] = useState<Lesson | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setCompleted(JSON.parse(saved));
    } catch {
      setCompleted([]);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(completed));
  }, [completed]);

  const allLessons = useMemo(() => phases.flatMap(p => p.lessons), []);
  const total = allLessons.length;
  const percent = Math.round(completed.length / total * 100);

  // A phase unlocks only after every lesson in the previous phase
  // has been completed successfully.
  const unlockedThrough = phases.reduce((highest, phase) => {
    if (phase.id === highest + 1 &&
        (phase.id === 1 ||
         phases[phase.id - 2].lessons.every(l => completed.includes(l.id)))) {
      return phase.id;
    }
    return highest;
  }, 0);

  function openLesson(lesson: Lesson) {
    const lessonPhase = phases.find(p => p.lessons.some(l => l.id === lesson.id));
    if (!lessonPhase || lessonPhase.id > unlockedThrough) return;
    setActiveLesson(lesson);
    setSelected(null);
    setChecked(false);
  }

  function finishLesson() {
    if (!activeLesson || !checked || selected !== activeLesson.answer) return;
    setCompleted(prev => prev.includes(activeLesson.id) ? prev : [...prev, activeLesson.id]);
    setActiveLesson(null);
    setSelected(null);
    setChecked(false);
  }

  function resetProgress() {
    if (window.confirm("Reset all Learn course progress on this browser?")) {
      setCompleted([]);
      setActiveLesson(null);
    }
  }

  const currentPhase = phases.find(p => p.lessons.some(l => l.id === activeLesson?.id));

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 pb-12">
      <section className="rounded-3xl border border-[#303030] bg-[#1a1a1a] p-6 md:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-[#a0a0a0]">
              <GraduationCap size={16}/> GREEDY STOCKS ACADEMY
            </div>
            <h1 className="text-3xl font-bold text-white md:text-4xl">Your learning journey.</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#b0b0b0]">
              From absolute stock-market basics to understanding risk and building portfolios.
              Learn at your own pace. No real-money investment required.
            </p>
          </div>
          <div className="rounded-2xl border border-[#303030] bg-[#000000] p-4">
            <Trophy className="mb-2 text-emerald-400" size={22}/>
            <div className="text-2xl font-bold text-white">{percent}%</div>
            <div className="text-xs text-[#999]">Course completed</div>
          </div>
        </div>
        <div className="mt-6">
          <div className="mb-2 flex justify-between text-xs text-[#aaa]">
            <span>{completed.length} of {total} lessons completed</span>
            <span>{total - completed.length} remaining</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[#444]">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{width: `${percent}%`}}/>
          </div>
        </div>
      </section>

      {activeLesson ? (
        <section className="rounded-3xl border border-[#303030] bg-[#1a1a1a] p-5 md:p-8">
          <button onClick={() => setActiveLesson(null)} className="mb-6 text-sm text-[#aaa] hover:text-white">? Back to all phases</button>
          <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-emerald-400">
            Phase {currentPhase?.id} ? {currentPhase?.title}
          </div>
          <h2 className="text-2xl font-bold text-white md:text-3xl">{activeLesson.title}</h2>
          <div className="mt-6 space-y-5">
            <div className="rounded-2xl bg-[#000000] p-5">
              <h3 className="mb-2 text-sm font-bold text-white">Let's understand</h3>
              <p className="text-sm leading-7 text-[#c7c7c7]">{activeLesson.explanation}</p>
            </div>
            <div className="rounded-2xl border border-[#3d4c42] bg-[#202b24] p-5">
              <h3 className="mb-2 text-sm font-bold text-emerald-300">A simple example</h3>
              <p className="text-sm leading-7 text-[#d0d0d0]">{activeLesson.example}</p>
            </div>
            <div className="rounded-2xl bg-[#000000] p-5">
              <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white"><CircleHelp size={17}/> Check your understanding</div>
              <p className="mb-4 text-sm text-[#ddd]">{activeLesson.question}</p>
              <div className="space-y-2">
                {activeLesson.options.map((option, i) => (
                  <button key={i} disabled={checked} onClick={() => setSelected(i)}
                    className={`w-full rounded-xl border p-3 text-left text-sm transition ${
                      checked && i === activeLesson.answer ? "border-emerald-500 bg-emerald-950/40 text-emerald-200" :
                      checked && selected === i ? "border-red-500 bg-red-950/30 text-red-200" :
                      selected === i ? "border-[#aaa] bg-[#383838] text-white" :
                      "border-[#303030] text-[#c4c4c4] hover:bg-[#2a2a2a]"
                    }`}>
                    <span className="mr-3 text-xs text-[#888]">{String.fromCharCode(65+i)}.</span>{option}
                  </button>
                ))}
              </div>
              {checked && (
                <div className={`mt-4 rounded-xl p-4 text-sm ${selected === activeLesson.answer ? "bg-emerald-950/40 text-emerald-200" : "bg-red-950/30 text-red-200"}`}>
                  <strong>{selected === activeLesson.answer ? "Correct!" : "Not quite."}</strong>
                  <p className="mt-1">{activeLesson.takeaway}</p>
                </div>
              )}
              <div className="mt-5 flex flex-wrap gap-3">
                {!checked ? (
                  <button disabled={selected === null} onClick={() => setChecked(true)}
                    className="rounded-xl bg-white px-5 py-3 text-sm font-bold text-black disabled:cursor-not-allowed disabled:opacity-40">
                    Check answer
                  </button>
                ) : selected === activeLesson.answer ? (
                  <button onClick={finishLesson} className="rounded-xl bg-emerald-500 px-5 py-3 text-sm font-bold text-black">
                    Complete lesson <CheckCircle2 className="ml-2 inline" size={16}/>
                  </button>
                ) : (
                  <button onClick={() => {setSelected(null);setChecked(false);}} className="rounded-xl bg-white px-5 py-3 text-sm font-bold text-black">
                    Try again
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-white">The five learning phases</h2>
              <p className="mt-1 text-sm text-[#999]">Choose a phase and learn one lesson at a time.</p>
            </div>
            <button onClick={resetProgress} className="flex items-center gap-2 rounded-xl border border-[#303030] px-3 py-2 text-xs text-[#aaa] hover:text-white">
              <RotateCcw size={14}/> Reset progress
            </button>
          </div>
          <div className="space-y-3">
            {phases.map(phase => {
              const done = phase.lessons.filter(l => completed.includes(l.id)).length;
              const locked = phase.id > unlockedThrough;
              const open = expanded === phase.id && !locked;
              return (
                <section key={phase.id} className={`overflow-hidden rounded-2xl border border-[#303030] bg-[#1a1a1a] ${locked ? "opacity-55" : ""}`}>
                  <button disabled={locked} onClick={() => setExpanded(open ? 0 : phase.id)}
                    className={`flex w-full items-center gap-4 p-5 text-left ${locked ? "cursor-not-allowed" : "hover:bg-[#2a2a2a]"}`}>
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#303030] text-lg font-bold text-white">
                      {locked ? <Lock size={18}/> : phase.id}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-white">Phase {phase.id} ? {phase.title} {locked ? "? LOCKED" : ""}</h3>
                      <p className="mt-1 text-xs leading-5 text-[#999]">{phase.description}</p>
                      <div className="mt-2 flex items-center gap-2 text-[11px] text-[#aaa]">
                        <span>{done}/{phase.lessons.length} lessons</span>
                        <span>?</span><span>{Math.round(done/phase.lessons.length*100)}% complete</span>
                      </div>
                    </div>
                    {open ? <ChevronDown size={19} className="text-[#aaa]"/> : <ChevronRight size={19} className="text-[#aaa]"/>}
                  </button>
                  {open && (
                    <div className="border-t border-[#303030] p-3 md:p-4">
                      {phase.lessons.map((lesson, index) => {
                        const isDone = completed.includes(lesson.id);
                        return (
                          <button key={lesson.id} onClick={() => openLesson(lesson)}
                            className="flex w-full items-center gap-3 rounded-xl p-3 text-left transition hover:bg-[#2a2a2a]">
                            {isDone ? <CheckCircle2 className="shrink-0 text-emerald-400" size={19}/> :
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[#555] text-xs text-[#aaa]">{index+1}</div>}
                            <span className={`min-w-0 flex-1 text-sm ${isDone ? "text-emerald-300" : "text-[#ddd]"}`}>{lesson.title}</span>
                            {isDone ? <span className="text-[10px] text-emerald-400">COMPLETED</span> :
                              <Play size={14} className="shrink-0 text-[#888]"/>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
          <div className="rounded-2xl border border-[#303030] bg-[#1a1a1a] p-5 text-xs leading-6 text-[#999]">
            <BookOpen className="mb-2 text-emerald-400" size={19}/>
            <strong className="text-[#ddd]">Learning note</strong>
            <p>Educational content only. Examples are simplified for learning and are not investment recommendations. Market rules and figures can change; consult official sources for current information.</p>
          </div>
        </>
      )}
    </div>
  );
}
