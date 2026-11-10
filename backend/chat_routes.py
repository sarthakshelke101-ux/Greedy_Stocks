
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from backend.database import engine
from analytics.market_ideas import generate_market_ideas
from analytics.ask_greedy.orchestrator import build_calculation_context
from analytics.ask_greedy.greedy_knowledge import build_greedy_knowledge_context
from analytics.ask_greedy.historical_intelligence import build_historical_intelligence_context
from analytics.ask_greedy.greedy_v2_evidence import build_greedy_v2_evidence_context
from analytics.ask_greedy.financial_education import build_education_context
from analytics.ask_greedy.real_world_research import (
    build_real_world_research_context,
)
from analytics.ask_greedy.research_planner import (
    build_research_plan,
    execute_research_plan,
    format_execution_context,
)


router = APIRouter(tags=["Ask GREEDY"])
logger = logging.getLogger("greedy_stocks_chat")

DEV_USER_EMAIL = "local-dev@greedystocks.local"

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

SYSTEM_INSTRUCTION = """
You are GREEDY, the AI-powered learning and research assistant
for GREEDY STOCKS.

PRODUCT SCOPE:
- You cover ONLY NIFTY 50 companies and the NIFTY 50 index.
- Do not provide research on NIFTY Next 50 or other indices.
- You help beginners understand the Indian stock market.
- Communicate naturally in English, Hindi, or Marathi according
  to the user's language.

YOUR RESPONSIBILITIES:
- Explain financial concepts in simple language.
- Explain verified historical financial research supplied
  in the application context.
- Answer follow-up questions using the conversation history.
- Explain risk, volatility, returns, drawdown and Sharpe ratio.
- Be friendly, patient and educational.

STRICT FINANCIAL SAFEGUARDS:
- The application supplies verified financial context.
- Treat that context as the only authoritative source for
  GREEDY STOCKS historical financial figures.
- Never invent prices, returns, dates, ratios, company data,
  financial statements or market events.
- Never alter supplied figures. For arithmetic or portfolio calculations using user-provided inputs, use the deterministic calculation result provided in the calculation context. Never invent missing inputs.
- If a figure is missing, explicitly say it is unavailable.
- Do not claim a company is undervalued or overvalued without
  verified fundamental and valuation data.
- Historical performance is not a forecast.
- Never promise profits or guaranteed returns.
- Do not provide personalised investment recommendations.
- Clearly distinguish educational explanations from
  investment advice.
- If the user asks about a company outside NIFTY 50, explain
  that the product currently focuses only on NIFTY 50.

BACKTEST DISCLOSURES:
When relevant, explain that:
- Historical results do not guarantee future performance.
- Latest monthly constituent snapshots may be used.
- Historical membership may not be fully reconstructed.
- Corporate-action coverage may be partial.
- Dividends may be excluded.
- Backtests may exclude transaction costs and slippage.
- Greedy Algorithm experiments are not guaranteed to
  outperform the benchmark.

RESPONSE STYLE:
- Friendly and conversational.
- Beginner-friendly explanations.
- Use headings and bullet points where useful.
- Explain technical terms when first introduced.
- Do not overwhelm beginners with unnecessary jargon.
- Never claim to have accessed live market data unless
  the application explicitly supplies it.
"""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    user_message: str
    assistant_message: str
    created_at: datetime


# --------------------------------------------------
# USER MANAGEMENT
# --------------------------------------------------

def get_or_create_dev_user(connection):
    user_id = connection.execute(
        text("""
            SELECT id
            FROM app_users
            WHERE email = :email
        """),
        {"email": DEV_USER_EMAIL},
    ).scalar_one_or_none()

    if user_id is not None:
        return user_id

    result = connection.execute(
        text("""
            INSERT INTO app_users (
                username,
                email,
                preferred_language,
                experience_level
            )
            VALUES (
                'GREEDY Development User',
                :email,
                'English',
                'Complete Beginner'
            )
        """),
        {"email": DEV_USER_EMAIL},
    )

    return result.lastrowid


# --------------------------------------------------
# CONVERSATION HISTORY
# --------------------------------------------------

def get_recent_history(conversation_id):
    if conversation_id is None:
        return []

    with engine.connect() as connection:
        user_id = connection.execute(
            text("""
                SELECT id
                FROM app_users
                WHERE email = :email
            """),
            {"email": DEV_USER_EMAIL},
        ).scalar_one_or_none()

        if user_id is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        exists = connection.execute(
            text("""
                SELECT id
                FROM conversations
                WHERE id = :conversation_id
                  AND user_id = :user_id
            """),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        ).scalar_one_or_none()

        if exists is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        rows = connection.execute(
            text("""
                SELECT role, content
                FROM messages
                WHERE conversation_id = :conversation_id
                  AND role IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT 10
            """),
            {"conversation_id": conversation_id},
        ).mappings().all()

    # Restore chronological order.
    return list(reversed(rows))


# --------------------------------------------------
# QUESTION UNDERSTANDING
# --------------------------------------------------

def detect_period(question: str) -> str:
    q = question.lower()

    if re.search(r"\b(1y|1 year|one year|12 months)\b", q):
        return "1Y"

    if re.search(r"\b(6m|6 months|six months)\b", q):
        return "6M"

    if re.search(r"\b(1m|1 month|one month|30 days)\b", q):
        return "1M"

    return "3M"



def detect_intents(question: str) -> list[str]:
    q = question.lower()
    intents = []

    if any(word in q for word in [
        "undervalued", "overvalued", "valuation",
        "fundamental", "fundamentals", "balance sheet", "earnings",
    ]):
        intents.append("FUNDAMENTAL_RESEARCH")

    if re.search(r"\b(?:p/e|pe)\s+ratio\b", q):
        intents.append("FUNDAMENTAL_RESEARCH")

    if any(word in q for word in [
    ]):
        intents.append("FUNDAMENTAL_RESEARCH")

    if any(word in q for word in [
        "greedy algorithm", "greedy picks",
        "greedy selection", "algorithm experiment",
        "greedy portfolio",
    ]):
        intents.append("GREEDY_PICKS")

    if any(word in q for word in [
        "sector performance", "best performing sectors",
        "top performing sectors", "sector returns",
        "which sectors performed", "sectors",
    ]):
        intents.append("SECTOR_PERFORMANCE")

    if any(word in q for word in [
        "best performing", "top performing",
        "performed best", "top performers",
        "best performers", "top stocks",
        "best stocks", "highest returns",
        "highest return", "performance",
        "performers", "historical returns",
        "stock returns", "gainers", "most profitable",
    ]):
        intents.append("PERFORMANCE_STANDOUTS")

    if any(word in q for word in [
        "volatility", "drawdown", "sharpe",
        "risk", "stable", "stability",
        "least volatile", "lowest volatility",
    ]):
        intents.append("RISK_AND_STABILITY")

    education_concepts = [
        "volatility", "sharpe", "drawdown", "diversification",
        "correlation", "beta", "liquidity", "risk return",
        "risk-reward", "risk reward", "cagr",
    ]
    education_phrases = [
        "what is", "explain", "meaning of", "teach me",
        "beginner", "difference between", "how does",
        "why does", "help me understand",
    ]

    if (
        any(term in q for term in education_concepts)
        and any(phrase in q for phrase in education_phrases)
    ):
        intents.append("EDUCATION")

    if not intents and any(word in q for word in [
        "nifty 50", "what is nifty",
        "explain nifty", "stock market basics",
    ]):
        intents.append("EDUCATION")

    unique_intents = list(dict.fromkeys(intents))

    # Pure educational questions must not trigger market research.
    # Preserve mixed education + explicit stock research questions.
    if "EDUCATION" in unique_intents:
        research_actions = [
            "show", "list", "rank", "compare", "analyse",
            "analyze", "analysis of", "top performing",
            "best performing", "worst performing",
            "which stocks", "stocks with", "stock-wise",
            "performance of", "historical returns of",
            "least volatile stocks", "lowest volatility stocks",
            "portfolio", "sector performance",
        ]

        has_research_action = any(
            term in q for term in research_actions
        )

        if not has_research_action:
            return ["EDUCATION"]

    return unique_intents or ["GENERAL"]


def detect_intent(question: str) -> str:
    """Backward-compatible single-intent interface."""
    return detect_intents(question)[0]


# --------------------------------------------------
# VERIFIED FINANCIAL CONTEXT
# --------------------------------------------------

def format_insights(ideas, metadata, category, comparison=None):
    categories = (
        [category] if isinstance(category, str)
        else list(category)
    )

    lines = []

    for current_category in categories:
        selected = [
            idea for idea in ideas
            if idea.get("category") == current_category
            and idea.get("status") == "AVAILABLE"
        ]

        if not selected:
            lines.append(
                f"{current_category}: No sufficient verified "
                "financial insight is available in this report."
            )
            lines.append("")
            continue

        lines.append(f"===== {current_category} =====")

        for index, idea in enumerate(selected, start=1):
            evidence = idea.get("evidence") or {}

            lines.append(
                f"{index}. {idea.get('title', 'Historical insight')}"
            )
            lines.append(
                f"What: {idea.get('what', 'Not available')}"
            )

            if idea.get("why"):
                lines.append(f"Why: {idea['why']}")

            fields = [
                ("period_return_pct", "Historical return", "%"),
                ("annualized_volatility_pct", "Annualised volatility", "%"),
                ("maximum_drawdown_pct", "Maximum drawdown", "%"),
                ("sharpe_ratio", "Sharpe ratio", ""),
                ("observations", "Return observations", ""),
            ]

            for key, label, suffix in fields:
                value = evidence.get(key)
                if value is not None:
                    lines.append(f"{label}: {value}{suffix}")

            if idea.get("risk"):
                lines.append(f"Risk: {idea['risk']}")

            lines.append("")

    required_categories = {
        "PERFORMANCE_STANDOUTS",
        "RISK_AND_STABILITY",
    }

    if comparison and required_categories.issubset(set(categories)):
        lines.extend([
            "DETERMINISTIC STOCK COMPARISON",
            "The following union and overlap were constructed by Python.",
            "Each stock appears once; category order is preserved.",
            "",
            "| Symbol | Return (%) | Volatility (%) | Drawdown (%) | Sharpe | Category |",
            "|---|---:|---:|---:|---:|---|",
        ])

        for stock in comparison.get("stocks", []):
            def cell(value, suffix=""):
                if value is None:
                    return "Not available"
                if isinstance(value, (int, float)):
                    return f"{value:.4f}{suffix}"
                return str(value)

            membership = " + ".join(stock.get("categories", []))

            lines.append(
                f"| {stock['symbol']} "
                f"| {cell(stock.get('period_return_pct'), '%')} "
                f"| {cell(stock.get('annualized_volatility_pct'), '%')} "
                f"| {cell(stock.get('maximum_drawdown_pct'), '%')} "
                f"| {cell(stock.get('sharpe_ratio'))} "
                f"| {membership} |"
            )

        overlap = comparison.get("overlap_symbols", [])
        overlap_text = ", ".join(overlap) if overlap else "None"

        lines.extend([
            "",
            f"Unique stocks in comparison: {comparison.get('stock_count', 0)}",
            f"Stocks appearing in both lists: {overlap_text}",
            "",
        ])

    lines.extend([
        "DATA METHODOLOGY",
        f"Index: {metadata.get('index')}",
        f"Period: {metadata.get('period')}",
        f"Historical start date: {metadata.get('requested_start_date')}",
        f"Historical end date: {metadata.get('common_end_date')}",
        f"Data as of: {metadata.get('data_as_of')}",
        f"Snapshot month: {metadata.get('snapshot_month')}",
        f"Price basis: {metadata.get('price_basis')}",
        (
            "Corporate-action coverage: "
            f"{metadata.get('corporate_action_coverage')}"
        ),
        f"Dividend adjusted: {metadata.get('dividend_adjusted')}",
        "",
        "IMPORTANT DISCLOSURES",
        "These are historical observations, not forecasts.",
        "The universe uses the latest monthly NIFTY 50 snapshot.",
        "Historical daily membership is not reconstructed.",
        "Corporate-action coverage is partial.",
    ])

    return "\\n".join(lines)


def build_financial_context(question):
    intents = detect_intents(question)

    if intents == ["FUNDAMENTAL_RESEARCH"]:
        return (
            "QUESTION CATEGORY: FUNDAMENTAL RESEARCH\\n\\n"
            "VERIFIED DATA STATUS:\\n"
            "Company fundamentals and valuation data are not yet "
            "integrated into GREEDY STOCKS.\\n"
            "Historical share-price performance cannot establish "
            "whether a company is undervalued or overvalued.\\n"
            "Do not invent financial statements, revenue, profit, "
            "debt, cash flow or valuation ratios.\\n"
            "You may explain what data would be needed for "
            "a proper fundamental analysis."
        )

    if intents == ["EDUCATION"]:
        return build_education_context(question)


    if intents == ["GENERAL"]:
        return (
            "QUESTION CATEGORY: GENERAL GREEDY STOCKS HELP\\n"
            "GREEDY STOCKS currently supports historical NIFTY 50 "
            "performance, volatility, drawdown, sector performance, "
            "historical Greedy Algorithm experiments and financial "
            "education. Fundamental valuation data is not yet integrated."
        )

    period = detect_period(question)

    try:
        report = generate_market_ideas(
            period=period,
            top_n=5,
        )

        verified_context = format_insights(
            ideas=report["ideas"],
            metadata=report["metadata"],
            category=intents,
            comparison=report.get("comparison"),
        )

        education_context = (
            build_education_context(
                question,
                ideas=report["ideas"],
                metadata=report["metadata"],
            )
            if "EDUCATION" in intents
            else ""
        )

        return (
            f"QUESTION CATEGORIES: {', '.join(intents)}\\n"
            f"REQUESTED PERIOD: {period}\\n\\n"
            "THE FOLLOWING IS VERIFIED APPLICATION DATA. "
            "Do not modify or invent its figures.\\n\\n"
            f"{verified_context}"
            + (
                "\\n\\n" + education_context
                if education_context else ""
            )
        )

    except Exception:
        logger.exception(
            "Financial intelligence generation failed."
        )
        return (
            "VERIFIED FINANCIAL DATA IS CURRENTLY UNAVAILABLE. "
            "Do not invent rankings, returns or risk metrics."
        )


def generate_gemini_answer(question, financial_context, history):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured.")
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        # PHASE 2: Unified dependency-aware research planning.
        research_plan, planning_status = build_research_plan(
            client=client,
            model=GEMINI_MODEL,
            question=question,
            history=history,
        )

        handlers = {
            "market_research": lambda query: financial_context,
            "latest_price": lambda query: build_real_world_research_context(
                query, "latest_price"
            ),
            "affordability": lambda query: build_real_world_research_context(
                query, "affordability"
            ),
            "calculation": lambda query: build_calculation_context(
                client=client,
                model=GEMINI_MODEL,
                question=query,
            ),
            "historical_analysis": lambda query: (
                build_historical_intelligence_context(
                    client=client,
                    model=GEMINI_MODEL,
                    question=query,
                )
            ),
            "greedy_knowledge": lambda query: (
                build_greedy_knowledge_context(question=query)
            ),
            "greedy_v2_evidence": lambda query: (
                build_greedy_v2_evidence_context(query)
            ),
        }

        execution_log = execute_research_plan(
            plan=research_plan,
            handlers=handlers,
        )

        research_plan_context = format_execution_context(
            plan=research_plan,
            planning_status=planning_status,
            execution_log=execution_log,
        )

        def operation_result(operation_name, default):
            for entry in execution_log:
                if entry["operation"] == operation_name:
                    if entry["status"] == "COMPLETED":
                        return str(entry["result"])
                    return (
                        f"{default}\nOperation status: {entry['status']}\n"
                        f"Reason: {entry.get('reason', 'Unavailable')}"
                    )
            return default

        calculation_context = operation_result(
            "calculation",
            "No deterministic calculation was requested by the research plan.",
        )

        greedy_knowledge_context = operation_result(
            "greedy_knowledge",
            "No GREEDY source-code research was requested.",
        )

        historical_company_context = operation_result(
            "historical_analysis",
            "No company-specific historical analysis was requested.",
        )

        greedy_v2_evidence_context = operation_result(
            "greedy_v2_evidence",
            "No GREEDY V2 experiment research was requested.",
        )



        conversation_text = ""

        for item in history:
            role = item["role"].upper()
            content = item["content"]

            conversation_text += (
                f"\n{role}: {content}\n"
            )

        prompt = f"""
VERIFIED APPLICATION CONTEXT:

{financial_context}

UNIFIED PHASE 2 RESEARCH PLAN:

{research_plan_context}

COMPANY-SPECIFIC HISTORICAL INTELLIGENCE:
{historical_company_context}

GREEDY V2 EXPERIMENT AND WALK-FORWARD EVIDENCE:
{greedy_v2_evidence_context}

GREEDY SOURCE-CODE KNOWLEDGE:

{greedy_knowledge_context}

SOURCE KNOWLEDGE RULES:
- Use source excerpts to explain actual Greedy implementation.
- Distinguish Greedy V1, V2 and V3 only when the source supports it.
- Explain selection logic, objective functions, constraints and limitations
  only when visible in the supplied code.
- If a requested version or implementation is not found, say so.
- Never claim to have run an algorithm merely because its source was read.
- Never change algorithm behaviour or portfolio-generation decisions.
- Never invent source files, functions, metrics or algorithm features.


DETERMINISTIC CALCULATION ENGINE OUTPUT:

{calculation_context}

CALCULATION RULES:
- If status is CALCULATED, use the exact result and supplied inputs.
- Explain the formula, units and assumptions.
- Do not alter or invent calculated values.
- If no calculation was executed, do not claim one was verified.
- User-provided mathematical inputs do not require external market data.
- Distinguish mathematical examples from actual market observations.


RECENT CONVERSATION HISTORY:
{conversation_text if conversation_text else "No previous messages."}

CURRENT USER QUESTION:
{question}

INSTRUCTIONS:
Answer the current question directly.

Use the verified application context for all financial figures.
If the context says data is unavailable, do not invent it.
Use conversation history to understand follow-up questions.
Explain concepts in beginner-friendly language.
Keep the answer clear, useful and conversational.

CONTEXTUAL EDUCATION RULES:
- When contextual financial education is supplied, teach the concept first.
- Then connect it to the supplied historical stock metrics where available.
- Explain what the metric means in plain language before interpreting values.
- Never imply that low volatility means no risk or capital protection.
- Never imply that a high Sharpe ratio guarantees future performance.
- For diversification, correlation, beta, liquidity or CAGR, clearly state
  when the corresponding verified metric is unavailable.
- Do not invent benchmark comparisons, portfolio holdings or correlations.
- Use a small numerical example only if it is clearly labelled illustrative,
  not an actual GREEDY STOCKS observation.
- Do not convert an educational explanation into a buy/sell recommendation.

COMPARATIVE FINANCIAL RESEARCH RULES:
- When multiple research categories are requested, present each category separately.
- When two or more categories contain stock-level metrics, include a
  consolidated comparison table covering every available returned stock.
- The table should include stock symbol, historical return, annualised
  volatility, maximum drawdown, Sharpe ratio and category membership.
- Mark category membership as Performance, Low Volatility, Both, or the
  applicable verified category names.
- Identify overlap by matching exact stock symbols, not company-name guesses.
- Do not omit stocks merely to shorten the table.
- Use only figures present in VERIFIED APPLICATION CONTEXT.
- If a metric is unavailable, write "Not available"; never estimate it.
- Distinguish lowest volatility from lowest overall risk.
- Explain that Sharpe ratio measures excess return per unit of volatility.
  It does not prove investment skill or predict future performance.
- Do not describe historical rankings as investment recommendations.
- If only one category is requested, do not force an unnecessary comparison.
"""

        interaction = client.interactions.create(
            model=GEMINI_MODEL,
            input=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
        )

        answer = interaction.output_text

        if not answer or not answer.strip():
            logger.warning("Gemini returned an empty response.")
            return None

        return answer.strip()

    except Exception:
        logger.exception("Gemini API request failed.")
        return None


# --------------------------------------------------
# MAIN RESPONSE ENGINE
# --------------------------------------------------

def generate_greedy_answer(question, history):
    financial_context = build_financial_context(question)

    # Deterministic fallback is always available.
    fallback_answer = financial_context

    ai_answer = generate_gemini_answer(
        question=question,
        financial_context=financial_context,
        history=history,
    )

    if ai_answer:
        return ai_answer

    logger.warning(
        "Using deterministic fallback response."
    )

    return (
        "GREEDY AI is temporarily unavailable, so I'm "
        "showing the verified application information instead.\n\n"
        f"{fallback_answer}"
    )


# --------------------------------------------------
# SEND CHAT MESSAGE
# --------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def send_message(request: ChatRequest):
    question = request.message.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        # Validate existing conversation and load its history.
        history = get_recent_history(request.conversation_id)

        # Generate the answer before opening the write transaction.
        answer = generate_greedy_answer(
            question=question,
            history=history,
        )

        with engine.begin() as connection:
            user_id = get_or_create_dev_user(connection)

            if request.conversation_id is None:
                result = connection.execute(
                    text("""
                        INSERT INTO conversations (
                            user_id,
                            title
                        )
                        VALUES (
                            :user_id,
                            :title
                        )
                    """),
                    {
                        "user_id": user_id,
                        "title": question[:255],
                    },
                )

                conversation_id = result.lastrowid

            else:
                conversation_id = request.conversation_id

            connection.execute(
                text("""
                    INSERT INTO messages (
                        conversation_id,
                        role,
                        content
                    )
                    VALUES (
                        :conversation_id,
                        'user',
                        :content
                    )
                """),
                {
                    "conversation_id": conversation_id,
                    "content": question,
                },
            )

            connection.execute(
                text("""
                    INSERT INTO messages (
                        conversation_id,
                        role,
                        content
                    )
                    VALUES (
                        :conversation_id,
                        'assistant',
                        :content
                    )
                """),
                {
                    "conversation_id": conversation_id,
                    "content": answer,
                },
            )

            connection.execute(
                text("""
                    UPDATE conversations
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = :conversation_id
                """),
                {"conversation_id": conversation_id},
            )

        return ChatResponse(
            conversation_id=conversation_id,
            user_message=question,
            assistant_message=answer,
            created_at=datetime.now(timezone.utc),
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception("Chat message processing failed.")

        raise HTTPException(
            status_code=500,
            detail="Chat service failed. Check backend logs.",
        )




# --------------------------------------------------
# LIST CONVERSATIONS
# --------------------------------------------------

@router.get("/chat/conversations")
def list_conversations(limit: int = 100):
    """
    Return the development user's recent conversations,
    newest activity first, with a short latest-message preview.
    """
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 200.",
        )

    try:
        with engine.connect() as connection:
            user_id = connection.execute(
                text("""
                    SELECT id
                    FROM app_users
                    WHERE email = :email
                """),
                {"email": DEV_USER_EMAIL},
            ).scalar_one_or_none()

            if user_id is None:
                return {"conversations": []}

            rows = connection.execute(
                text("""
                    SELECT
                        c.id,
                        c.title,
                        c.created_at,
                        c.updated_at,
                        (
                            SELECT m.content
                            FROM messages AS m
                            WHERE m.conversation_id = c.id
                            ORDER BY m.id DESC
                            LIMIT 1
                        ) AS last_message,
                        (
                            SELECT COUNT(*)
                            FROM messages AS mc
                            WHERE mc.conversation_id = c.id
                        ) AS message_count
                    FROM conversations AS c
                    WHERE c.user_id = :user_id
                    ORDER BY c.updated_at DESC, c.id DESC
                    LIMIT :limit
                """),
                {
                    "user_id": user_id,
                    "limit": limit,
                },
            ).mappings().all()

            return {
                "conversations": [
                    dict(row) for row in rows
                ]
            }

    except Exception:
        logger.exception("Conversation list retrieval failed.")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve conversation history.",
        )


# --------------------------------------------------
# RETRIEVE CONVERSATION
# --------------------------------------------------

@router.get("/chat/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    try:
        with engine.connect() as connection:
            user_id = connection.execute(
                text("""
                    SELECT id
                    FROM app_users
                    WHERE email = :email
                """),
                {"email": DEV_USER_EMAIL},
            ).scalar_one_or_none()

            if user_id is None:
                raise HTTPException(
                    status_code=404,
                    detail="User not found.",
                )

            conversation = connection.execute(
                text("""
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE id = :conversation_id
                      AND user_id = :user_id
                """),
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                },
            ).mappings().first()

            if conversation is None:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                )

            messages = connection.execute(
                text("""
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE conversation_id = :conversation_id
                    ORDER BY id ASC
                """),
                {"conversation_id": conversation_id},
            ).mappings().all()

            return {
                "conversation": dict(conversation),
                "messages": [dict(message) for message in messages],
            }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Conversation retrieval failed.")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve conversation.",
        )


# --------------------------------------------------
# DELETE CONVERSATION
# --------------------------------------------------

@router.delete("/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: int):
    """
    Delete one conversation belonging to the development user
    and all of its messages.
    """
    try:
        with engine.begin() as connection:
            user_id = connection.execute(
                text("""
                    SELECT id
                    FROM app_users
                    WHERE email = :email
                """),
                {"email": DEV_USER_EMAIL},
            ).scalar_one_or_none()

            if user_id is None:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                )

            exists = connection.execute(
                text("""
                    SELECT id
                    FROM conversations
                    WHERE id = :conversation_id
                      AND user_id = :user_id
                """),
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                },
            ).scalar_one_or_none()

            if exists is None:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                )

            connection.execute(
                text("""
                    DELETE FROM messages
                    WHERE conversation_id = :conversation_id
                """),
                {"conversation_id": conversation_id},
            )

            connection.execute(
                text("""
                    DELETE FROM conversations
                    WHERE id = :conversation_id
                      AND user_id = :user_id
                """),
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                },
            )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "message": "Conversation deleted successfully.",
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Conversation deletion failed.")
        raise HTTPException(
            status_code=500,
            detail="Could not delete conversation.",
        )
