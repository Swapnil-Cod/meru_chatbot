from flask import Blueprint, request, jsonify, render_template
from app.db import get_db
from openai import OpenAI
import json
import re
from datetime import datetime, date, timedelta
from decimal import Decimal

main = Blueprint("main", __name__)

# ==================== TRADING TERM MAPPINGS ====================
TERM_MAPPINGS = {
    "1 lac": "100000",
    "1 lakh": "100000",
    "1 lak": "100000",
    "one lakh": "100000",
    "drawdown": "peak equity minus current equity",
    "equity curve": "cumulative sum of PnL starting from initial capital",
    "sharpe ratio": "(average return / standard deviation of returns) * sqrt(252)",
    "win rate": "(profitable_count / trade_count) * 100",
    "today": "current day trades",
    "live": "today's intraday positions",
    "open positions": "trades where selltime IS NULL",
    "max dd": "maximum drawdown",
    "roi": "return on investment",
    "pnl": "profit and loss",
}

# ==================== QUERY TEMPLATES ====================
QUERY_TEMPLATES = {
    "equity_curve": """
        SELECT order_date,
               SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + {initial_capital} as equity
        FROM slip_positionlive_daily
        WHERE mode = '{mode}'
        GROUP BY order_date
        ORDER BY order_date
    """,

    "drawdown": """
        SELECT order_date,
               SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + {initial_capital} as equity,
               MAX(SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + {initial_capital})
                   OVER (ORDER BY order_date) as peak_equity,
               MAX(SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + {initial_capital})
                   OVER (ORDER BY order_date) -
               SUM(SUM(total_pnl)) OVER (ORDER BY order_date) - {initial_capital} as drawdown
        FROM slip_positionlive_daily
        WHERE mode = '{mode}'
        GROUP BY order_date
        ORDER BY order_date
    """,

    "win_rate_by_strategy": """
        SELECT strategy_name,
               SUM(trade_count) as total_trades,
               SUM(profitable_count) as wins,
               (SUM(profitable_count) / SUM(trade_count) * 100) as win_rate_pct
        FROM slip_positionlive_daily
        GROUP BY strategy_name
        ORDER BY win_rate_pct DESC
    """,
}

# OpenAI client will be initialized lazily
_openai_client = None

def get_openai_client():
    """Lazy initialization of OpenAI client"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()  # Reads OPENAI_API_KEY from environment
    return _openai_client

def fix_sql_query_with_error(sql_query, error_message, user_question):
    """Ask AI to fix a SQL query based on the error message"""
    client = get_openai_client()

    prompt = f"""The following SQL query failed with an error. Please fix it and return ONLY the corrected SQL query.

Original User Question: {user_question}

Failed SQL Query:
{sql_query}

Error Message:
{error_message}

Common issues to check:
- Invalid column names
- Incorrect table names
- Syntax errors
- Missing GROUP BY clauses for aggregated columns
- Division by zero
- Incorrect date functions

Return ONLY the fixed SQL query, nothing else."""

    try:
        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )

        fixed_query = completion.choices[0].message.content.strip()
        fixed_query = re.sub(r'^```sql\s*|\s*```$', '', fixed_query, flags=re.MULTILINE)
        fixed_query = re.sub(r'^```\s*|\s*```$', '', fixed_query, flags=re.MULTILINE)

        return fixed_query
    except Exception as e:
        print(f"Error fixing SQL query: {e}")
        return None

def serialize_results(results):
    """Convert database results to JSON-serializable format"""
    if not results:
        return results

    serialized = []
    for row in results:
        serialized_row = {}
        for key, value in row.items():
            # Convert non-serializable types
            if isinstance(value, Decimal):
                serialized_row[key] = float(value)
            elif isinstance(value, (datetime, date)):
                serialized_row[key] = value.isoformat()
            elif isinstance(value, timedelta):
                # Convert timedelta to string (HH:MM:SS format)
                total_seconds = int(value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                serialized_row[key] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                serialized_row[key] = value
        serialized.append(serialized_row)

    return serialized

# Database schema for the AI to understand
DB_SCHEMA = """
=== TABLE 1: trading_all (Historical Data - All Completed Trades) ===
Purpose: Contains all historical trading data. Use this for historical analysis.
Columns:
- order_id (bigint, primary key)
- ordertime (datetime) - when the order was placed (use DATE(ordertime) for date filtering)
- strategy_name (varchar) - name of trading strategy
- broker (varchar) - broker name
- account_id (int) - account identifier
- mode (enum: 'PAPER', 'PROD') - trading mode
- equity (decimal) - equity amount
- underlying (varchar) - underlying asset (e.g., NIFTY, BANKNIFTY)
- expiration (varchar) - option expiration date
- strike (decimal) - strike price
- right (varchar) - option right (C for Call, P for Put)
- leg (decimal) - leg number in multi-leg strategy
- ticker (varchar) - ticker symbol
- side (varchar) - BUY/SELL/short
- lots (int) - number of lots
- buyprice (decimal) - buy price
- sellprice (decimal) - sell price
- buy_slippage_value (decimal) - slippage cost on buy
- sell_slippage_value (decimal) - slippage cost on sell
- mtm (decimal) - mark to market P&L
- realized (decimal) - realized profit/loss
- total_pnl (decimal) - total profit and loss (primary P&L metric)
- quantity (int) - order quantity
- quantity_filled (int) - quantity filled
- quantity_exited (int) - quantity exited
- buytime (datetime) - when position was bought
- selltime (datetime) - when position was sold
- remarks (varchar) - additional remarks
- last_updated (datetime) - last update timestamp

=== TABLE 2: trading_today (Today's Live Data - Intraday Positions) ===
Purpose: Contains only today's trading data. Emptied at end of day (data moved to trading_all).
Use this for "today", "current", "live", "intraday" questions.
Columns: Same as trading_all (identical schema)

=== TABLE 3: slip_positionlive_daily (Daily Performance Summary) ===
Purpose: Aggregated daily performance by broker, account, strategy. Use for performance analysis, win rates, strategy comparisons.
Columns:
- id (bigint, primary key)
- broker (varchar) - broker name
- account_id (int) - account identifier
- strategy_name (varchar) - name of trading strategy
- order_date (date) - trading date
- mode (enum: 'PAPER', 'PROD') - trading mode
- equity (decimal) - max equity for that day
- lots (int) - total lots traded
- buy_slippage_value (decimal) - total buy slippage
- sell_slippage_value (decimal) - total sell slippage
- mtm (decimal) - total mark to market
- realized (decimal) - total realized P&L
- total_pnl (decimal) - total profit/loss for the day
- quantity (int) - total quantity
- quantity_filled (int) - total quantity filled
- quantity_exited (int) - total quantity exited
- trade_count (int) - number of trades (short side only)
- profitable_count (int) - number of profitable trades (short side, total_pnl > 0)
- last_refreshed (datetime) - when aggregation was last run

KEY INSIGHTS:
- Win Rate = (profitable_count / trade_count) * 100
- Use slip_positionlive_daily for strategy performance, win rates, ROI
- Use trading_all for detailed trade analysis, historical trends
- Use trading_today for current day live positions

TRADING METRICS DEFINITIONS:
1. Maximum Drawdown: Largest peak-to-trough decline in equity
   - Formula: MAX(peak_equity - current_equity)
   - Use window functions: MAX() OVER (ORDER BY date)

2. Equity Curve: Running total of capital over time
   - Start with initial capital: 100000 (1 lakh for PROD mode)
   - Formula: initial_capital + SUM(daily_pnl) OVER (ORDER BY date)

3. Sharpe Ratio: Risk-adjusted return measure
   - Formula: (AVG(daily_return) / STDDEV(daily_return)) * SQRT(252)
   - Higher is better (>1 is good, >2 is excellent)

4. Win Rate: Percentage of profitable trades
   - Formula: (profitable_count / trade_count) * 100
   - Available in slip_positionlive_daily table

5. ROI (Return on Investment): Percentage return on capital
   - Formula: (total_pnl / initial_capital) * 100

6. Average Win/Loss: Average profit per winning/losing trade
   - Use CASE statements to filter profitable vs unprofitable trades

IMPORTANT: Do NOT use order_date column in trading_all. Always use DATE(ordertime) for date comparisons.
"""

def translate_to_sql(user_question, conversation_history=None):
    """Use OpenAI to translate natural language to SQL with conversation context"""
    client = get_openai_client()

    system_prompt = f"""You are a SQL expert. Convert natural language questions to MySQL queries.

Database Schema:
{DB_SCHEMA}

Rules:
1. Only generate SELECT queries (no INSERT, UPDATE, DELETE)
2. Use proper MySQL syntax
3. Return ONLY the SQL query, nothing else
4. Use backticks for column names with special characters
5. For profit questions, use 'total_pnl' or 'realized' columns
6. CRITICAL: For date filtering, ALWAYS use DATE(ordertime) - NEVER use order_date column
7. Always limit results to reasonable amounts (e.g., LIMIT 100)
8. Format dates properly for MySQL
9. IMPORTANT: If the user asks a follow-up question (like "what was the ticker" or "show me more details"),
   use the context from previous questions and queries to understand what they're referring to.
10. For EQUITY CURVE queries: Use SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000 (starting capital 1 lakh)
11. For DRAWDOWN queries: Calculate as peak_equity - current_equity using window functions
12. Initial capital is always 100000 (1 lakh) for PROD mode
13. Use slip_positionlive_daily table for equity curves and drawdown (faster than trading_all)

Examples:

=== Historical Data Queries (trading_all) ===
Q: "What was my total profit yesterday?"
A: SELECT SUM(total_pnl) as profit FROM trading_all WHERE DATE(ordertime) = CURDATE() - INTERVAL 1 DAY;

Q: "Show me my top 5 profitable trades"
A: SELECT order_id, ticker, total_pnl, ordertime FROM trading_all ORDER BY total_pnl DESC LIMIT 5;

Q: "When was the first day I started trading and what was the profit?"
A: SELECT DATE(MIN(ordertime)) as first_day, SUM(total_pnl) as profit FROM trading_all WHERE DATE(ordertime) = (SELECT DATE(MIN(ordertime)) FROM trading_all);

Q: "Show me all trades from March 2025"
A: SELECT * FROM trading_all WHERE DATE(ordertime) BETWEEN '2025-03-01' AND '2025-03-31' LIMIT 100;

=== Today's Live Data (trading_today) ===
Q: "What's my profit today?"
A: SELECT SUM(total_pnl) as profit FROM trading_today;

Q: "Show me my current open positions"
A: SELECT order_id, ticker, strategy_name, buyprice, mtm, total_pnl FROM trading_today WHERE selltime IS NULL;

Q: "How many trades have I done today?"
A: SELECT COUNT(*) as trade_count FROM trading_today;

=== Performance Summary (slip_positionlive_daily) ===
Q: "What's the win rate for each strategy?"
A: SELECT strategy_name, SUM(trade_count) as total_trades, SUM(profitable_count) as wins, (SUM(profitable_count) / SUM(trade_count) * 100) as win_rate_pct FROM slip_positionlive_daily GROUP BY strategy_name;

Q: "Which strategy performed best last week?"
A: SELECT strategy_name, SUM(total_pnl) as total_profit, SUM(trade_count) as trades FROM slip_positionlive_daily WHERE order_date >= CURDATE() - INTERVAL 7 DAY GROUP BY strategy_name ORDER BY total_profit DESC LIMIT 1;

Q: "Show me daily performance for the last 30 days"
A: SELECT order_date, SUM(total_pnl) as daily_pnl, SUM(trade_count) as trades, (SUM(profitable_count) / SUM(trade_count) * 100) as win_rate FROM slip_positionlive_daily WHERE order_date >= CURDATE() - INTERVAL 30 DAY GROUP BY order_date ORDER BY order_date;

Q: "Compare broker performance this month"
A: SELECT broker, SUM(total_pnl) as profit, SUM(trade_count) as trades FROM slip_positionlive_daily WHERE order_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01') GROUP BY broker ORDER BY profit DESC;

=== Equity Curve & Drawdown Queries (Advanced) ===
Q: "Show me equity curve starting with 1 lakh" OR "Chart my equity over time"
A: SELECT order_date, SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000 as equity FROM slip_positionlive_daily WHERE mode = 'PROD' GROUP BY order_date ORDER BY order_date;

Q: "Show drawdown chart" OR "Chart maximum drawdown" OR "Show me a chart of maximum drawdown"
A: SELECT order_date,
       SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000 as equity,
       MAX(SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000) OVER (ORDER BY order_date) as peak_equity,
       (MAX(SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000) OVER (ORDER BY order_date)) - (SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000) as drawdown
FROM slip_positionlive_daily
WHERE mode = 'PROD'
GROUP BY order_date
ORDER BY order_date;

Q: "What is my maximum drawdown percentage?"
A: WITH equity_curve AS (
    SELECT order_date,
           SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000 as equity,
           MAX(SUM(SUM(total_pnl)) OVER (ORDER BY order_date) + 100000) OVER (ORDER BY order_date) as peak_equity
    FROM slip_positionlive_daily
    WHERE mode = 'PROD'
    GROUP BY order_date
)
SELECT MAX((peak_equity - equity) / peak_equity * 100) as max_drawdown_pct FROM equity_curve;

=== Risk Metrics & Advanced Analytics ===
Q: "Calculate my Sharpe ratio" OR "What is my Sharpe ratio?"
A: WITH daily_returns AS (
    SELECT order_date, SUM(total_pnl) as daily_pnl
    FROM slip_positionlive_daily
    WHERE mode = 'PROD'
    GROUP BY order_date
)
SELECT (AVG(daily_pnl) / STDDEV(daily_pnl)) * SQRT(252) as sharpe_ratio FROM daily_returns;

Q: "What is my ROI?" OR "Calculate return on investment"
A: SELECT (SUM(total_pnl) / 100000 * 100) as roi_percentage FROM slip_positionlive_daily WHERE mode = 'PROD';

Q: "Show me average win and average loss"
A: SELECT
    AVG(CASE WHEN total_pnl > 0 THEN total_pnl END) as avg_win,
    AVG(CASE WHEN total_pnl < 0 THEN total_pnl END) as avg_loss,
    AVG(CASE WHEN total_pnl > 0 THEN total_pnl END) / ABS(AVG(CASE WHEN total_pnl < 0 THEN total_pnl END)) as win_loss_ratio
FROM trading_all;

Q: "Chart my rolling 7-day profit average"
A: SELECT order_date,
       SUM(total_pnl) as daily_pnl,
       AVG(SUM(total_pnl)) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as rolling_7day_avg
FROM slip_positionlive_daily
WHERE mode = 'PROD'
GROUP BY order_date
ORDER BY order_date;

Q: "What are my best and worst trading days?"
A: (SELECT order_date, SUM(total_pnl) as pnl, 'Best' as type FROM slip_positionlive_daily WHERE mode = 'PROD' GROUP BY order_date ORDER BY pnl DESC LIMIT 5)
UNION ALL
(SELECT order_date, SUM(total_pnl) as pnl, 'Worst' as type FROM slip_positionlive_daily WHERE mode = 'PROD' GROUP BY order_date ORDER BY pnl ASC LIMIT 5)
ORDER BY pnl DESC;

Q: "Compare strategy risk-adjusted returns"
A: SELECT strategy_name,
       SUM(total_pnl) as total_profit,
       (SUM(profitable_count) / SUM(trade_count) * 100) as win_rate,
       SUM(total_pnl) / STDDEV(total_pnl) as risk_adjusted_return
FROM slip_positionlive_daily
WHERE mode = 'PROD'
GROUP BY strategy_name
ORDER BY risk_adjusted_return DESC;

Follow-up Example:
Previous Q: "What was my biggest loss?"
Previous SQL: SELECT * FROM trading_all ORDER BY total_pnl ASC LIMIT 1;
Previous Result: Shows trade with ticker='NIFTY', total_pnl=-5000, ordertime='2024-01-15 10:30:00'

Current Q: "what was the ticker"
A: SELECT ticker FROM trading_all ORDER BY total_pnl ASC LIMIT 1;
"""

    # Build messages with conversation context
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history if available
    if conversation_history:
        for entry in conversation_history:
            messages.append({"role": "user", "content": f"Question: {entry['question']}"})
            if entry.get('sql_query'):
                messages.append({"role": "assistant", "content": f"SQL: {entry['sql_query']}"})
            if entry.get('result_summary'):
                messages.append({"role": "assistant", "content": f"Result: {entry['result_summary']}"})

    # Add current question
    messages.append({"role": "user", "content": user_question})

    completion = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=messages,
        temperature=0.1
    )

    sql_query = completion.choices[0].message.content.strip()
    # Remove markdown code blocks if present
    sql_query = re.sub(r'^```sql\s*|\s*```$', '', sql_query, flags=re.MULTILINE)
    sql_query = re.sub(r'^```\s*|\s*```$', '', sql_query, flags=re.MULTILINE)
    return sql_query.strip()

def format_results_with_ai(user_question, sql_query, results):
    """Use OpenAI to format SQL results into natural language"""
    client = get_openai_client()

    system_prompt = """You are a helpful assistant that explains database query results in natural language.
Given a user's question, the SQL query that was run, and the results, provide a clear, concise answer.
Be friendly and conversational. Format numbers nicely (e.g., use commas for thousands, 2 decimal places for money)."""

    user_prompt = f"""Question: {user_question}

SQL Query executed: {sql_query}

Results: {json.dumps(results, default=str)}

Please provide a natural language answer to the user's question based on these results."""

    completion = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    return completion.choices[0].message.content

def detect_chart_type(user_question, results):
    """Detect if user explicitly requested a chart and determine chart type"""
    if not results or len(results) == 0:
        print("❌ Chart detection: No results")
        return None

    # Show charts if user explicitly asks for visualization OR query looks chart-worthy
    chart_keywords = ['chart', 'plot', 'graph', 'visualize', 'show me a', 'trend', 'over time', 'curve', 'drawdown']
    export_keywords = ['excel', 'csv', 'export', 'download']

    user_question_lower = user_question.lower()
    has_chart_keyword = any(keyword in user_question_lower for keyword in chart_keywords)
    has_export_keyword = any(keyword in user_question_lower for keyword in export_keywords)

    # Auto-detect chart-worthy queries even without explicit keywords
    auto_chart_indicators = ['equity', 'profit trend', 'performance', 'comparison', 'daily', 'monthly', 'rolling']
    has_auto_chart_indicator = any(indicator in user_question_lower for indicator in auto_chart_indicators)

    # If user asks for export/excel/csv, show export buttons (with optional chart)
    # If user asks for chart/plot/graph, show chart
    # Also show chart if query has auto-chart indicators and returns time-series data
    print(f"📊 Chart detection: has_chart={has_chart_keyword}, has_export={has_export_keyword}, has_auto={has_auto_chart_indicator}")

    if not (has_chart_keyword or has_export_keyword or has_auto_chart_indicator):
        print("❌ Chart detection: No chart/export keywords found")
        return None  # No visualization request = no chart/export

    # Basic validation
    row_count = len(results)
    # Allow charts for 1-1000 rows (removed upper limit restriction)
    # Single row is OK for metrics like "What is my Sharpe ratio?"
    if row_count == 0 or row_count > 1000:
        return None

    columns = list(results[0].keys())
    numeric_cols = []
    date_cols = []

    for col in columns:
        sample_val = results[0][col]
        if isinstance(sample_val, (int, float)) and not isinstance(sample_val, bool):
            numeric_cols.append(col)
        elif 'date' in col.lower() or 'time' in col.lower():
            date_cols.append(col)

    if len(numeric_cols) == 0:
        print("❌ Chart detection: No numeric columns found")
        return None

    print(f"✅ Chart detection proceeding: {row_count} rows, numeric_cols={numeric_cols}, date_cols={date_cols}")

    # If only export requested, return export-only config
    if has_export_keyword and not has_chart_keyword:
        return {
            'visualize': False,
            'show_export': True
        }

    # If chart requested or auto-detected, determine chart type with AI
    if has_chart_keyword or has_auto_chart_indicator:
        client = get_openai_client()
        sample_data = results[:3] if len(results) >= 3 else results

        prompt = f"""The user explicitly asked for a chart. Determine the best chart type.

User Question: {user_question}
Columns: {columns}
Sample Data: {json.dumps(sample_data, default=str)}
Total Rows: {len(results)}

Chart type rules:
- Time series (date/datetime column + numeric column) = "line"
- Equity curves, drawdowns, trends over time = "line"
- Comparisons (categories + numeric values) = "bar"
- Distributions (categories + values showing proportions, 3-10 rows) = "pie"
- Single metric value = "bar" (show as simple bar)
- Multiple time-based rows (>5 rows with dates) = "line"
- Default = "bar"

Respond ONLY with JSON:
{{"chart_type": "line|bar|pie", "x_column": "column_name", "y_column": "column_name", "label_column": "column_name"}}
"""

        try:
            completion = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )

            response_text = completion.choices[0].message.content.strip()
            response_text = re.sub(r'^```json\s*|\s*```$', '', response_text, flags=re.MULTILINE)
            response_text = re.sub(r'^```\s*|\s*```$', '', response_text, flags=re.MULTILINE)

            chart_config = json.loads(response_text)
            chart_config['visualize'] = True
            chart_config['show_export'] = True

            return chart_config
        except Exception as e:
            print(f"Error detecting chart type: {e}")
            return None

    return None

@main.route("/")
def home():
    """Serve the chat interface"""
    return render_template("index.html")

@main.route("/chat", methods=["POST"])
def chat():
    """Enhanced chatbot that can query the trading database"""
    user_input = (request.json or {}).get("message", "")

    if not user_input:
        return jsonify({"error": "message is required"}), 400

    try:
        # Step 1: Translate natural language to SQL
        sql_query = translate_to_sql(user_input, None)

        # Debug logging
        print(f"\n{'='*60}")
        print(f"USER: {user_input}")
        print(f"GENERATED SQL: {sql_query}")
        print(f"{'='*60}\n")

        # Clean up the SQL query - sometimes AI adds extra text
        sql_lines = sql_query.strip().split('\n')
        # Find the line that starts with SELECT and collect all subsequent lines until we hit a semicolon or end
        actual_sql = None
        collecting = False
        sql_parts = []

        for line in sql_lines:
            line_stripped = line.strip()
            if line_stripped.upper().startswith('SELECT'):
                collecting = True

            if collecting:
                sql_parts.append(line_stripped)
                # Stop if we hit a line ending with semicolon
                if line_stripped.endswith(';'):
                    break

        if sql_parts:
            actual_sql = ' '.join(sql_parts)

        if actual_sql:
            sql_query = actual_sql

        # Debug: print cleaned SQL
        print(f"CLEANED SQL: {sql_query}")

        # Safety check: only allow SELECT queries
        if not sql_query.strip().upper().startswith('SELECT'):
            error_msg = f"Only SELECT queries are allowed for safety."
            return jsonify({
                "error": error_msg
            }), 400

        # Step 2: Execute the query with retry logic
        conn = get_db()
        max_retries = 2
        results = None

        for attempt in range(max_retries):
            try:
                with conn.cursor() as cur:
                    cur.execute(sql_query)
                    results = cur.fetchall()
                break  # Success, exit retry loop
            except Exception as db_error:
                error_msg = str(db_error)
                print(f"Query execution failed (attempt {attempt + 1}/{max_retries}): {error_msg}")

                if attempt < max_retries - 1:
                    # Try to fix the query
                    print(f"Attempting to fix SQL query...")
                    fixed_query = fix_sql_query_with_error(sql_query, error_msg, user_input)

                    if fixed_query and fixed_query != sql_query:
                        print(f"Retrying with fixed query: {fixed_query}")
                        sql_query = fixed_query
                    else:
                        print("Could not generate a fixed query, using original")
                        break
                else:
                    # Final attempt failed
                    raise

        # Serialize results for JSON compatibility
        serialized_results = serialize_results(results)

        # Step 3: Detect if results should be visualized
        chart_config = None
        if serialized_results and len(serialized_results) > 0:
            chart_config = detect_chart_type(user_input, serialized_results)

        # Step 4: Format results with AI
        if serialized_results:
            reply = format_results_with_ai(user_input, sql_query, serialized_results)
        else:
            reply = "I couldn't find any data matching your query. The database might be empty or the query returned no results."

        return jsonify({
            "response": reply,
            "sql_query": sql_query,
            "raw_results": serialized_results,
            "chart_config": chart_config
        })

    except Exception as e:
        # Log the error for debugging
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in chat endpoint: {error_details}")

        # If database query fails, fall back to general chat
        client = get_openai_client()
        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful financial trading assistant."},
                {"role": "user", "content": user_input},
            ]
        )
        reply = completion.choices[0].message.content

        return jsonify({
            "response": reply,
            "note": "Answered without database query - check server logs",
            "error": str(e)
        })
