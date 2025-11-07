# Trading Assistant Chatbot

A powerful AI-powered chatbot for analyzing trading data with natural language queries. Features a beautiful ChatGPT-style interface.

## 🚀 Quick Start

### 1. Start the Application
```bash
start.bat
```

### 2. Open in Browser
Navigate to: **http://127.0.0.1:5000**

## ✨ Features

- **Natural Language Queries** - Ask questions in plain English about your trading data
- **Interactive Charts** - Use keywords like "chart", "plot", "graph" to visualize data
- **Smart Chart Detection** - AI selects the best chart type (line, bar, pie) based on your data
- **Export Capabilities** - Use keywords like "excel", "csv", "export" to download data
- **SQL Transparency** - See the actual SQL queries being executed
- **Modern UI** - Beautiful ChatGPT-style interface
- **AI-Powered** - Uses OpenAI GPT to translate natural language to SQL and format results

## 📁 Project Structure

```
meru_chatbot/
├── static/
│   ├── css/style.css        # UI styling
│   └── js/chat.js          # Chat functionality
├── templates/
│   └── index.html          # Main interface
├── app/
│   ├── routes.py           # API endpoints & SQL translation
│   └── db.py               # Database connection
├── schema/
│   └── tables.sql          # Database schema
└── run.py                  # Application entry point
```

## 💡 Usage Examples

### Today's Live Data Queries
- "What is my profit today?"
- "Show me my current open positions"
- "How many trades have I done today?"
- "What's my total slippage today?"

### Strategy Performance Queries
- "What is the win rate for each strategy?"
- "Which strategy performed best last week?"
- "Compare broker performance this month"
- "Show me daily performance for the last 30 days"

### Historical Analysis Queries
- "When was the first day I started trading?"
- "What was my total profit last month?"
- "Show me my top 10 most profitable trades"
- "What was my biggest loss and what was the ticker?"

### Chart Queries (Use Keywords: chart, plot, graph, visualize)
- "**Chart** my profit trend over the last 30 days" → Line chart
- "**Plot** strategy win rates" → Bar chart
- "**Visualize** profit by broker" → Bar chart
- "Show profit distribution by ticker as a **graph**" → Pie chart

### Export Queries (Use Keywords: excel, csv, export, download)
- "Give me my top trades and **export to CSV**" → CSV download
- "Show strategy performance in **Excel** format" → CSV download
- "**Download** today's trading data" → CSV download

## 🔧 Configuration

1. Create a `.env` file with your database credentials:
```env
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=merucapus
DB_PORT=3307
OPENAI_API_KEY=your_openai_api_key
```

2. Ensure your SSH tunnel is configured (if connecting to remote database):
```env
SSH_HOST=your_remote_host
SSH_PORT=22
SSH_USER=ubuntu
SSH_KEY_FILE=path/to/your/key.pem
```

## 📊 Database Schema

Your database should have three tables (see `schema/tables.sql` for complete schema):

### 1. **trading_all** - Historical Trading Data
Contains all completed historical trades. Use for historical analysis and trends.
- Key columns: `order_id`, `ordertime`, `strategy_name`, `broker`, `account_id`, `ticker`, `total_pnl`, `buyprice`, `sellprice`
- Date filtering: Always use `DATE(ordertime)` for date comparisons

### 2. **trading_today** - Today's Live Data
Contains only today's trading data. Emptied at end of day when data is moved to `trading_all`.
- Same schema as `trading_all`
- Use for: "today", "current", "live", "intraday" queries

### 3. **slip_positionlive_daily** - Daily Performance Summary
Aggregated daily performance by broker, account, and strategy.
- Key columns: `broker`, `account_id`, `strategy_name`, `order_date`, `total_pnl`, `trade_count`, `profitable_count`
- Use for: win rates, strategy performance, ROI analysis
- Win Rate Formula: `(profitable_count / trade_count) * 100`
