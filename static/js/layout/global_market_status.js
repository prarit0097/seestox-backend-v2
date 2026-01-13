// ==================================================
// GLOBAL MARKET STATUS + SMART THROTTLING (FINAL)
// ==================================================

document.addEventListener("DOMContentLoaded", function () {

    const API_URL = "/market-snapshot/";
    let refreshTimer = null;
    let lastMarketState = null;

    const dot = document.getElementById("market-status");
    const text = document.getElementById("market-status-text");
    const timeEl = document.getElementById("last-updated");

    if (!dot || !text || !timeEl) {
        console.warn("Global market status elements missing");
        return;
    }

    // ===== IST TIME =====
    function getIST() {
        const now = new Date();
        const utc = now.getTime() + now.getTimezoneOffset() * 60000;
        return new Date(utc + 330 * 60000);
    }

    // ===== MARKET STATE =====
    function isMarketOpen() {
        const ist = getIST();
        const day = ist.getDay(); // 0=Sun ... 6=Sat
        if (day === 0 || day === 6) {
            return false;
        }
        const mins = ist.getHours() * 60 + ist.getMinutes();
        const open = 9 * 60 + 15;
        const close = 15 * 60 + 30;
        return mins >= open && mins <= close;
    }

    // ===== UI UPDATE =====
    function updateUI(isOpen) {
        if (isOpen) {
            dot.style.backgroundColor = "#22c55e";
            dot.style.boxShadow = "0 0 8px rgba(34, 197, 94, 0.7)";
            text.innerText = "MARKET OPEN";
        } else {
            dot.style.backgroundColor = "#ef4444";
            dot.style.boxShadow = "0 0 8px rgba(239, 68, 68, 0.7)";
            text.innerText = "MARKET CLOSED";
        }
    }

    function updateTime() {
        const ist = getIST();
        const hours = ist.getHours();
        const period = hours >= 12 ? "PM" : "AM";
        const h12 = hours % 12 || 12;
        const m = String(ist.getMinutes()).padStart(2, "0");
        timeEl.innerText = `Last updated: -- ${h12}.${m}${period}`;
    }

    // ===== API PING =====
    async function pingMarket() {
        try {
            const res = await fetch(API_URL);
            if (!res.ok) return;

            const data = await res.json();
            if (data.status !== "OK") return;

            if (typeof data.is_open === "boolean") {
                updateUI(data.is_open);
            } else {
                updateUI(isMarketOpen());
            }

            updateTime();
        } catch (e) {
            console.error("Market snapshot error:", e);
        }
    }

    // ===== SMART ENGINE =====
    function startEngine() {
        const marketOpen = isMarketOpen();

        // Only reset timer if market state changed
        if (lastMarketState !== marketOpen) {
            lastMarketState = marketOpen;

            if (refreshTimer) clearInterval(refreshTimer);

            const interval = marketOpen ? 3000 : 30000;

            updateUI(marketOpen);
            pingMarket();

            refreshTimer = setInterval(pingMarket, interval);
            console.log(
                marketOpen
                    ? "Market OPEN -> 3s refresh"
                    : "Market CLOSED -> 30s refresh"
            );
        }
    }

    // ===== INITIAL START =====
    startEngine();

    // Re-check market state every 60 sec
    setInterval(startEngine, 60000);

});




