// static/js/analyze.js
// PHASE-UI-3 — CONFIDENCE TREND ENABLED (SAFE)

function getCSRFToken() {
    let cookieValue = null;
    const name = "csrftoken";

    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }
    return cookieValue;
}


document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("stock-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const resultBox = document.getElementById("result");

    let loading = false;

    async function analyzeStock() {
        const company = input.value.trim();
        if (!company || loading) return;

        loading = true;
        resultBox.innerHTML = "<p>⏳ Analyzing stock...</p>";

        try {
            const res = await fetch("/analyze-stock/", {
            method: "POST",
            credentials: "include",   // ⭐⭐⭐ MOST IMPORTANT LINE ⭐⭐⭐
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify({ company })
                });

            // 🔐 HARD BLOCK HANDLING (TRIAL / PAID)
            if (res.status === 403) {
                const data = await res.json();
                resultBox.innerHTML = `
                    <p style="color:red;">❌ ${data.error}</p>
                    <p><b>Upgrade to continue using AIStockTool.</b></p>
                `;
                return;
            }

            const data = await res.json();
            renderResult(data);

        } catch (err) {
            console.error(err);
            resultBox.innerHTML = "<p>❌ Failed to analyze stock</p>";
        } finally {
            loading = false;
        }
    }

    analyzeBtn.addEventListener("click", analyzeStock);

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            analyzeStock();
        }
    });
});


// ==================================================
// RENDER RESULT
// ==================================================

function renderResult(d) {
    const box = document.getElementById("result");

    if (!d || !d.symbol) {
        box.innerHTML = "<p>❌ Invalid response</p>";
        return;
    }

    const decision = d.signal || "WAIT";

    // -----------------------------
    // SENTIMENT
    // -----------------------------
    const sentimentConfidence = Math.max(
        0,
        Math.min(100, Number(d.sentiment?.confidence ?? 0))
    );

    const sentimentTrend = Number(d.sentiment?.trend_7d ?? 0);
    const sentimentArrow =
        sentimentTrend > 0 ? "↑" :
        sentimentTrend < 0 ? "↓" : "→";

    const headlines = d.sentiment?.headlines ?? [];
    const headlinesHtml = headlines.length
        ? headlines.map(h => `<li>${h}</li>`).join("")
        : "<li>No relevant recent news</li>";

    // -----------------------------
    // CONFIDENCE TREND
    // -----------------------------
    const confTrend = d.confidence?.trend_7d || { delta: 0, direction: "STABLE" };
    const confArrow =
        confTrend.direction === "UP" ? "↑" :
        confTrend.direction === "DOWN" ? "↓" : "→";

    box.innerHTML = `
        <div class="card">
            <h2>${d.company} (${d.symbol})</h2>
            <h3>₹${d.current_price}</h3>
            <span class="badge ${decision.toLowerCase()}">${decision}</span>
        </div>

        <div class="card">
            <h3>📈 Trend Analysis</h3>
            <p>Trend: <b>${d.trend.trend}</b></p>
            <p>Strength: ${d.trend.strength}</p>
            <p>Volume: ${d.trend.volume_trend}</p>
            <p>Support: ₹${d.trend.support}</p>
            <p>Resistance: ₹${d.trend.resistance}</p>
        </div>

        <div class="card">
            <h3>🧠 Market Sentiment</h3>
            <p>Overall: <b>${d.sentiment.overall}</b></p>
            <p>Confidence: <b>${sentimentConfidence}%</b></p>
            <p><i>Sentiment Trend (7d):</i>
                <b>${sentimentTrend >= 0 ? "+" : ""}${sentimentTrend} ${sentimentArrow}</b>
            </p>
            <ul>${headlinesHtml}</ul>
        </div>

        <div class="card">
            <h3>⚠️ Risk Analysis</h3>
            <p>Risk Level: <b>${d.risk.risk_level}</b></p>
            <p>Risk Score: ${d.risk.risk_score}</p>
        </div>

        <div class="card">
            <h3>🔮 Prediction (Tomorrow)</h3>
            <p>Up: ${d.prediction.tomorrow.up_probability}%</p>
            <p>Sideways: ${d.prediction.tomorrow.sideways_probability}%</p>
            <p>Down: ${d.prediction.tomorrow.down_probability}%</p>
            <p>Expected Range: ${d.prediction.tomorrow.expected_range}</p>
        </div>

        <div class="card">
            <h3>📊 Historical Confidence</h3>
            <p>Success: ${d.confidence.success_rate}%</p>
            <p>Failure: ${d.confidence.failure_rate}%</p>
            <p>Neutral: ${d.confidence.neutral_rate}%</p>
            <p>Samples: ${d.confidence.sample_size}</p>
            <p>Verdict: <b>${d.confidence.verdict}</b></p>
            <p>
                <i>Confidence Trend (7d):</i>
                <b>${confTrend.delta >= 0 ? "+" : ""}${confTrend.delta} ${confArrow}</b>
            </p>
        </div>
    `;
}
