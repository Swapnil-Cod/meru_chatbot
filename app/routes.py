from flask import Blueprint, request, jsonify, render_template
from app.db import get_db
from openai import OpenAI
import json
import re
from datetime import datetime, date, timedelta
from decimal import Decimal

main = Blueprint("main", __name__)

# OpenAI client will be initialized lazily
_openai_client = None

def get_openai_client():
    """Lazy initialization of OpenAI client"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()  # Reads OPENAI_API_KEY from environment
    return _openai_client

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
Table: trading_all
Columns:
- order_id (bigint, primary key)
- ordertime (datetime) - when the order was placed (use DATE(ordertime) for date filtering)
- strategy_name (varchar) - name of trading strategy
- broker (varchar) - broker name
- account_id (int) - account identifier
- mode (enum: 'PAPER', 'PROD') - trading mode
- equity (decimal) - equity amount
- underlying (varchar) - underlying asset
- expiration (varchar) - option expiration date
- strike (decimal) - strike price
- right (varchar) - option right (C/P)
- leg (decimal) - leg number
- ticker (varchar) - ticker symbol
- side (varchar) - BUY/SELL
- lots (int) - number of lots
- buyprice (decimal) - buy price
- sellprice (decimal) - sell price
- mtm (decimal) - mark to market
- realized (decimal) - realized profit/loss
- total_pnl (decimal) - total profit and loss
- quantity (int) - order quantity
- buytime (datetime) - when position was bought
- selltime (datetime) - when position was sold
- remarks (varchar) - additional remarks
- last_updated (datetime) - last update timestamp

IMPORTANT: Do NOT use order_date column. Always use DATE(ordertime) for date comparisons.
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

Examples:
Q: "What was my total profit yesterday?"
A: SELECT SUM(total_pnl) as profit FROM trading_all WHERE DATE(ordertime) = CURDATE() - INTERVAL 1 DAY;

Q: "Show me my top 5 profitable trades"
A: SELECT order_id, ticker, total_pnl, ordertime FROM trading_all ORDER BY total_pnl DESC LIMIT 5;

Q: "When was the first day I started trading and what was the profit?"
A: SELECT DATE(MIN(ordertime)) as first_day, SUM(total_pnl) as profit FROM trading_all WHERE DATE(ordertime) = (SELECT DATE(MIN(ordertime)) FROM trading_all);

Q: "Show me all trades from March 2025"
A: SELECT * FROM trading_all WHERE DATE(ordertime) BETWEEN '2025-03-01' AND '2025-03-31' LIMIT 100;

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
        model="gpt-3.5-turbo",
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
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    return completion.choices[0].message.content

def detect_chart_type(user_question, results):
    """Detect if user explicitly requested a chart and determine chart type"""
    if not results or len(results) == 0:
        return None

    # ONLY show charts if user explicitly asks for visualization
    chart_keywords = ['chart', 'plot', 'graph', 'visualize']
    export_keywords = ['excel', 'csv', 'export', 'download']

    has_chart_keyword = any(keyword in user_question.lower() for keyword in chart_keywords)
    has_export_keyword = any(keyword in user_question.lower() for keyword in export_keywords)

    # If user asks for export/excel/csv, show export buttons (with optional chart)
    # If user asks for chart/plot/graph, show chart
    if not (has_chart_keyword or has_export_keyword):
        return None  # No visualization request = no chart/export

    # Basic validation
    row_count = len(results)
    if row_count == 1 or row_count > 50:
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
        return None

    # If only export requested, return export-only config
    if has_export_keyword and not has_chart_keyword:
        return {
            'visualize': False,
            'show_export': True
        }

    # If chart requested, determine chart type with AI
    if has_chart_keyword:
        client = get_openai_client()
        sample_data = results[:3] if len(results) >= 3 else results

        prompt = f"""The user explicitly asked for a chart. Determine the best chart type.

User Question: {user_question}
Columns: {columns}
Sample Data: {json.dumps(sample_data, default=str)}
Total Rows: {len(results)}

Chart type rules:
- Time series (date/datetime column + numeric column) = "line"
- Comparisons (categories + numeric values, 5-30 rows) = "bar"
- Distributions (categories + values showing proportions, 3-10 rows) = "pie"
- Default = "bar"

Respond ONLY with JSON:
{{"chart_type": "line|bar|pie", "x_column": "column_name", "y_column": "column_name", "label_column": "column_name"}}
"""

        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
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

        # Step 2: Execute the query
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(sql_query)
            results = cur.fetchall()

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
            model="gpt-3.5-turbo",
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
