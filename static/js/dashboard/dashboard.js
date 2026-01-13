// ============================================
// DASHBOARD MARKET SNAPSHOT ENGINE
// (Only index values & arrows – NO market status)
// ============================================

(function () {

    const API_URL = "/market-snapshot/";
    let refreshInterval = null;

    let previousValues = {
        nifty: null,
        sensex: null,
        vix: null
    };

    function renderValue(id, value, prev) {
        const el = document.getElementById(id);
        if (!el) return;

        let arrow = "";
        if (prev !== null) {
            if (value > prev) arrow = " ▲";
            else if (value < prev) arrow = " ▼";
        }

        el.innerText = `${value}%${arrow}`;
        el.style.color = value >= 0 ? "#22c55e" : "#ef4444";
    }

    async function fetchMarketSnapshot() {
        try {
            const res = await fetch(API_URL);
            if (!res.ok) return;

            const data = await res.json();
            if (data.status !== "OK") return;

            renderValue("nifty-value", data.nifty, previousValues.nifty);
            renderValue("sensex-value", data.sensex, previousValues.sensex);
            renderValue("vix-value", data.vix, previousValues.vix);

            previousValues = {
                nifty: data.nifty,
                sensex: data.sensex,
                vix: data.vix
            };

        } catch (err) {
            console.error("Dashboard snapshot error:", err);
        }
    }

    function startDashboardEngine() {
        // fixed safe refresh (dashboard only)
        const interval = 5000;

        if (refreshInterval) clearInterval(refreshInterval);

        fetchMarketSnapshot();
        refreshInterval = setInterval(fetchMarketSnapshot, interval);
    }

    // Start only after DOM is ready
    document.addEventListener("DOMContentLoaded", startDashboardEngine);

})();
