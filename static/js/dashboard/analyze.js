/**
 * analyze.js
 * ==========================================
 * AIStockTool – FINAL DASHBOARD MAPPER
 * Exact mapping with analyzer.py output
 * ==========================================
 */

document.addEventListener("DOMContentLoaded", () => {
    console.log("✅ analyze.js loaded successfully");

    const input = document.getElementById("stock-input");
    const analyzeBtn = document.getElementById("analyze-btn");

    const ui = {
        symbol: document.getElementById("signal-symbol"),
        action: document.getElementById("signal-action"),
        summary: document.getElementById("signal-summary"),
        confidence: document.getElementById("signal-confidence"),
        why: document.getElementById("why-text"),
        risk: document.getElementById("risk-text"),

        // 🔍 Prediction Transparency
        ptCorrect: document.getElementById("pt-correct"),
        ptWrong: document.getElementById("pt-wrong"),
        ptNeutral: document.getElementById("pt-neutral"),
        ptSamples: document.getElementById("pt-samples"),
        ptVerdict: document.getElementById("pt-verdict"),
    };

    if (!input || !analyzeBtn) {
        console.error("❌ Input / button missing");
        return;
    }

    const setText = (el, text) => {
        if (el) el.innerText = text;
    };

    const setAction = (action) => {
        if (!ui.action) return;

        ui.action.className = "badge";
        ui.action.innerText = action;

        if (action === "BUY") ui.action.classList.add("positive");
        else if (action === "SELL") ui.action.classList.add("negative");
        else ui.action.classList.add("neutral");
    };

    analyzeBtn.addEventListener("click", async () => {
        const symbol = input.value.trim().toUpperCase();
        if (!symbol) return alert("Enter stock name");

        // ============================
        // UI RESET
        // ============================
        setText(ui.symbol, symbol);
        setAction("WAIT");
        setText(ui.summary, "Analyzing market structure...");
        setText(ui.confidence, "—%");
        setText(ui.why, "—");
        setText(ui.risk, "—");

        setText(ui.ptCorrect, "Correct Predictions: —%");
        setText(ui.ptWrong, "Wrong Predictions: —%");
        setText(ui.ptNeutral, "Neutral Outcomes: —%");
        setText(ui.ptSamples, "Data Samples: —");
        setText(ui.ptVerdict, "AI Reliability: —");

        analyzeBtn.disabled = true;
        analyzeBtn.innerText = "Analyzing...";

        try {
            const res = await fetch("/analyze-stock/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken(),
                },
                body: JSON.stringify({ company: symbol }),
            });

            const data = await res.json();
            console.log("🟢 AI RESPONSE:", data);

            /* ============================
               1️⃣ FINAL SIGNAL
            ============================ */
            setAction(data.signal || "WAIT");

            /* ============================
               2️⃣ SUMMARY (TREND + VOLUME)
            ============================ */
            if (data.trend) {
                setText(
                    ui.summary,
                    `Trend: ${data.trend.trend} | Volume: ${data.trend.volume_trend}`
                );
            }

            /* ============================
               3️⃣ AI CONFIDENCE (SENTIMENT)
            ============================ */
            if (data.sentiment && typeof data.sentiment.confidence === "number") {
                setText(ui.confidence, data.sentiment.confidence + "%");
            }

            /* ============================
               4️⃣ WHY THIS SIGNAL
            ============================ */
            if (data.trend) {
                setText(
                    ui.why,
                    `Support ₹${data.trend.support} | Resistance ₹${data.trend.resistance}`
                );
            }

            /* ============================
               5️⃣ WORST CASE / RISK
            ============================ */
            if (data.risk) {
                setText(
                    ui.risk,
                    `Risk ${data.risk.risk_level} (Score ${data.risk.risk_score})`
                );
            }

            /* ============================
               6️⃣ PREDICTION TRANSPARENCY ✅
               (THIS WAS MISSING)
            ============================ */
            if (data.confidence) {
                const c = data.confidence;

                if (ui.ptCorrect)
                    ui.ptCorrect.innerText = `Correct Predictions: ${c.success_rate}%`;

                if (ui.ptWrong)
                    ui.ptWrong.innerText = `Wrong Predictions: ${c.failure_rate}%`;

                if (ui.ptNeutral)
                    ui.ptNeutral.innerText = `Neutral Outcomes: ${c.neutral_rate}%`;

                if (ui.ptSamples)
                    ui.ptSamples.innerText = `Data Samples: ${c.sample_size}`;

                if (ui.ptVerdict)
                    ui.ptVerdict.innerText = `AI Reliability: ${c.verdict}`;
            }

        } catch (err) {
            console.error("❌ Analyze failed:", err);
            setText(ui.summary, "AI unavailable");
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.innerText = "Analyze";
        }
    });
});

/* ============================
   CSRF TOKEN
============================ */
function getCSRFToken() {
    const token = document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="));
    return token ? token.split("=")[1] : "";
}
