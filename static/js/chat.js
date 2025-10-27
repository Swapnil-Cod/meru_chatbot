// Chat Application JavaScript

class ChatApp {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.isFirstMessage = true;

        this.init();
    }

    init() {
        // Focus input on load
        this.messageInput.focus();

        // Set up event listeners
        this.messageInput.addEventListener('keypress', (e) => this.handleKeyPress(e));
        this.sendButton.addEventListener('click', () => this.sendMessage());
    }

    handleKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    askQuestion(question) {
        this.messageInput.value = question;
        this.sendMessage();
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        // Clear welcome message on first interaction
        if (this.isFirstMessage) {
            this.chatMessages.innerHTML = '';
            this.isFirstMessage = false;
        }

        // Add user message
        this.addMessage(message, 'user');
        this.messageInput.value = '';

        // Disable input while processing
        this.messageInput.disabled = true;
        this.sendButton.disabled = true;

        // Show typing indicator
        const typingIndicator = this.addTypingIndicator();

        try {
            // Send request to backend
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message
                })
            });

            const data = await response.json();

            // Remove typing indicator
            typingIndicator.remove();

            // Add assistant response
            if (response.ok) {
                this.addMessage(data.response, 'assistant', data.sql_query, data.error, data.chart_config, data.raw_results);
            } else {
                this.addMessage(data.error || 'Sorry, something went wrong.', 'assistant', null, true);
            }
        } catch (error) {
            typingIndicator.remove();
            this.addMessage('Sorry, I couldn\'t connect to the server. Please try again.', 'assistant', null, true);
        } finally {
            // Re-enable input
            this.messageInput.disabled = false;
            this.sendButton.disabled = false;
            this.messageInput.focus();
        }
    }

    addMessage(text, sender, sqlQuery = null, error = null, chartConfig = null, rawResults = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Add message text
        const textP = document.createElement('p');
        textP.textContent = text;
        contentDiv.appendChild(textP);

        // Add chart if present
        if (chartConfig && rawResults) {
            // Show chart if visualize is true
            if (chartConfig.visualize) {
                const chartContainer = document.createElement('div');
                chartContainer.className = 'chart-container';
                chartContainer.id = `chart-${Date.now()}`;
                contentDiv.appendChild(chartContainer);

                // Render chart after adding to DOM
                setTimeout(() => {
                    this.renderChart(chartContainer.id, chartConfig, rawResults);
                }, 100);
            }

            // Show export buttons if show_export is true
            if (chartConfig.show_export) {
                const exportDiv = document.createElement('div');
                exportDiv.className = 'export-buttons';

                // Only show PNG export if there's a chart
                if (chartConfig.visualize) {
                    const chartId = `chart-${Date.now() - 100}`; // Match the chart ID above
                    const exportPNGBtn = document.createElement('button');
                    exportPNGBtn.className = 'export-btn';
                    exportPNGBtn.textContent = '📷 Export PNG';
                    exportPNGBtn.onclick = () => {
                        const containers = contentDiv.querySelectorAll('.chart-container');
                        if (containers.length > 0) {
                            this.exportChart(containers[containers.length - 1].id, 'png');
                        }
                    };
                    exportDiv.appendChild(exportPNGBtn);
                }

                // Always show CSV export if export is enabled
                const exportCSVBtn = document.createElement('button');
                exportCSVBtn.className = 'export-btn';
                exportCSVBtn.textContent = '📊 Export CSV';
                exportCSVBtn.onclick = () => this.exportCSV(rawResults);

                exportDiv.appendChild(exportCSVBtn);
                contentDiv.appendChild(exportDiv);
            }
        }

        // Add SQL query if present
        if (sqlQuery) {
            const sqlLabel = document.createElement('div');
            sqlLabel.className = 'sql-label';
            sqlLabel.textContent = 'SQL Query:';
            contentDiv.appendChild(sqlLabel);

            const sqlDiv = document.createElement('div');
            sqlDiv.className = 'sql-query';
            sqlDiv.textContent = sqlQuery;
            contentDiv.appendChild(sqlDiv);
        }

        // Add error message if present
        if (error && typeof error === 'string') {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = '⚠️ ' + error;
            contentDiv.appendChild(errorDiv);
        }

        messageDiv.appendChild(contentDiv);
        this.chatMessages.appendChild(messageDiv);

        // Scroll to bottom
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    addTypingIndicator() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';

        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator active';

        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('div');
            dot.className = 'typing-dot';
            typingDiv.appendChild(dot);
        }

        messageDiv.appendChild(typingDiv);
        this.chatMessages.appendChild(messageDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;

        return messageDiv;
    }

    // ==================== CHART RENDERING ====================

    renderChart(containerId, chartConfig, rawResults) {
        const container = document.getElementById(containerId);
        if (!container) return;

        try {
            const chartType = chartConfig.chart_type;
            const xCol = chartConfig.x_column;
            const yCol = chartConfig.y_column;
            const labelCol = chartConfig.label_column;

            let plotData = [];
            let layout = {
                autosize: true,
                margin: { l: 50, r: 30, t: 50, b: 80 },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { family: 'inherit' },
                hovermode: 'closest'
            };

            const config = {
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['lasso2d', 'select2d']
            };

            switch (chartType) {
                case 'line':
                    plotData = [{
                        x: rawResults.map(r => r[xCol]),
                        y: rawResults.map(r => r[yCol]),
                        type: 'scatter',
                        mode: 'lines+markers',
                        marker: { color: '#667eea', size: 8 },
                        line: { color: '#667eea', width: 2 }
                    }];
                    layout.title = 'Trend Over Time';
                    layout.xaxis = { title: xCol };
                    layout.yaxis = { title: yCol };
                    break;

                case 'bar':
                    plotData = [{
                        x: rawResults.map(r => r[labelCol || xCol]),
                        y: rawResults.map(r => r[yCol]),
                        type: 'bar',
                        marker: {
                            color: rawResults.map(r => r[yCol] >= 0 ? '#4caf50' : '#f44336'),
                            line: { width: 0 }
                        }
                    }];
                    layout.title = 'Comparison';
                    layout.xaxis = { title: labelCol || xCol };
                    layout.yaxis = { title: yCol };
                    break;

                case 'pie':
                    plotData = [{
                        labels: rawResults.map(r => r[labelCol || xCol]),
                        values: rawResults.map(r => r[yCol]),
                        type: 'pie',
                        marker: {
                            colors: ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b']
                        },
                        textinfo: 'label+percent',
                        hoverinfo: 'label+value+percent'
                    }];
                    layout.title = 'Distribution';
                    break;

                case 'scatter':
                    plotData = [{
                        x: rawResults.map(r => r[xCol]),
                        y: rawResults.map(r => r[yCol]),
                        mode: 'markers',
                        type: 'scatter',
                        marker: {
                            size: 10,
                            color: '#667eea',
                            opacity: 0.7
                        }
                    }];
                    layout.title = 'Scatter Plot';
                    layout.xaxis = { title: xCol };
                    layout.yaxis = { title: yCol };
                    break;
            }

            Plotly.newPlot(containerId, plotData, layout, config);
        } catch (error) {
            console.error('Error rendering chart:', error);
            container.innerHTML = '<p style="color: #f44; padding: 20px;">Failed to render chart</p>';
        }
    }

    exportChart(containerId, format) {
        try {
            if (format === 'png') {
                Plotly.downloadImage(containerId, {
                    format: 'png',
                    width: 1200,
                    height: 800,
                    filename: `trading_chart_${Date.now()}`
                });
            }
        } catch (error) {
            console.error('Error exporting chart:', error);
            alert('Failed to export chart');
        }
    }

    exportCSV(data) {
        try {
            if (!data || data.length === 0) {
                alert('No data to export');
                return;
            }

            // Get column headers
            const headers = Object.keys(data[0]);

            // Convert to CSV
            let csv = headers.join(',') + '\n';
            data.forEach(row => {
                const values = headers.map(header => {
                    let value = row[header];
                    // Handle values with commas or quotes
                    if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                        value = '"' + value.replace(/"/g, '""') + '"';
                    }
                    return value;
                });
                csv += values.join(',') + '\n';
            });

            // Create download link
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `trading_data_${Date.now()}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error('Error exporting CSV:', error);
            alert('Failed to export CSV');
        }
    }
}

// Initialize app when DOM is loaded
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new ChatApp();
});

// Global function for example queries (called from HTML)
function askQuestion(question) {
    if (app) {
        app.askQuestion(question);
    }
}
