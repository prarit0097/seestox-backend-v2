document.addEventListener("DOMContentLoaded", async () => {

    const params = new URLSearchParams(window.location.search);
    const company = params.get("company");
    
    if (!company) return;
    
    const res = await fetch("/analyze-stock/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRF()
        },
        credentials: "include",
        body: JSON.stringify({ company })
    });

    const d = await res.json();
    if (!d || !d.symbol) return;

    document.getElementById("stock-name").innerText =
        `${d.company} (${d.symbol})`;

    document.getElementById("stock-meta").innerText =
        `${d.exchange || "NSE"}  ${d.sector || ""}`;

    document.getElementById("stock-price").innerText =
        `₹${d.current_price}`;

    document.getElementById("ai-verdict").innerText =
        d.signal || "WAIT";

    // Trend
    document.getElementById("trend").innerText = d.trend.trend;
    document.getElementById("strength").innerText = d.trend.strength;
    document.getElementById("volume").innerText = d.trend.volume_trend;
    document.getElementById("support").innerText = d.trend.support;
    document.getElementById("resistance").innerText = d.trend.resistance;

    // Sentiment
    document.getElementById("sentiment-overall").innerText =
        d.sentiment.overall;

    document.getElementById("sentiment-confidence").innerText =
        d.sentiment.confidence + "%";

    const news = document.getElementById("sentiment-news");
    news.innerHTML = "";
    d.sentiment.headlines.forEach(h => {
        const li = document.createElement("li");
        li.innerText = h;
        news.appendChild(li);
    });

    // Prediction
    document.getElementById("bearish").innerText =
        d.prediction.tomorrow.down_probability + "%";

    document.getElementById("sideways").innerText =
        d.prediction.tomorrow.sideways_probability + "%";

    document.getElementById("bullish").innerText =
        d.prediction.tomorrow.up_probability + "%";

    document.getElementById("expected-range").innerText =
        `Expected Range: ${d.prediction.tomorrow.expected_range}`;

    // Risk
    document.getElementById("risk-level").innerText =
        d.risk.risk_level;

    document.getElementById("risk-score").innerText =
        d.risk.risk_score;

    // Confidence
    document.getElementById("conf-success").innerText =
        d.confidence.success_rate + "%";

    document.getElementById("conf-failure").innerText =
        d.confidence.failure_rate + "%";

    document.getElementById("conf-neutral").innerText =
        d.confidence.neutral_rate + "%";

    document.getElementById("conf-samples").innerText =
        d.confidence.sample_size;

    document.getElementById("conf-verdict").innerText =
        d.confidence.verdict;




    // ================= RISK COLOR LOGIC =================
const riskEl = document.getElementById("risk-level");

riskEl.classList.remove("risk-low", "risk-medium", "risk-high");

if (d.risk.risk_level === "LOW") {
    riskEl.classList.add("risk-low");
}
else if (d.risk.risk_level === "MEDIUM") {
    riskEl.classList.add("risk-medium");
}
else if (d.risk.risk_level === "HIGH") {
    riskEl.classList.add("risk-high");
}


const bearishVal = parseInt(
        document.getElementById("bearish")?.innerText || 0
    );
    const sidewaysVal = parseInt(
        document.getElementById("sideways")?.innerText || 0
    );
    const bullishVal = parseInt(
        document.getElementById("bullish")?.innerText || 0
    );

    const bearishBar = document.getElementById("bearish-bar");
    const sidewaysBar = document.getElementById("sideways-bar");
    const bullishBar = document.getElementById("bullish-bar");

    // Small delay for smooth load animation
    setTimeout(() => {
        if (bearishBar) bearishBar.style.width = bearishVal + "%";
        if (sidewaysBar) sidewaysBar.style.width = sidewaysVal + "%";
        if (bullishBar) bullishBar.style.width = bullishVal + "%";
    }, 300);
});

function getCSRF() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken"))
        ?.split("=")[1];
}


