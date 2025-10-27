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

### Text Queries
- "When was the first day I started trading?"
- "What was my total profit last month?"
- "How many trades did I make today?"
- "What was my biggest loss and what was the ticker?"

### Chart Queries (Use Keywords: chart, plot, graph, visualize)
- "**Chart** my profit trend over the last 30 days" → Line chart
- "**Plot** my top 10 most profitable trades" → Bar chart
- "**Visualize** profit by strategy" → Bar chart
- "Show profit distribution by ticker as a **graph**" → Pie chart

### Export Queries (Use Keywords: excel, csv, export, download)
- "Give me my top trades and **export to CSV**" → CSV download
- "Show all March trades in **Excel** format" → CSV download
- "**Download** my trading data" → CSV download

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

2. Ensure your trading data is in the `trading_all` table (see `schema/tables.sql`)

## 📊 Database Schema

Your database should have:
- **trading_all** - Main trading data table (see `schema/tables.sql` for complete schema)
