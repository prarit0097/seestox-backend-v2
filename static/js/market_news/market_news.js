document.addEventListener("DOMContentLoaded", () => {

    const feed = document.querySelector(".news-feed");
    const refreshBtn = document.querySelector(".news-refresh"); // 🔥 THIS
    const searchInput = document.querySelector(".news-search input");
    const filterButtons = document.querySelectorAll(".news-filters button");
    const marketStatusEl = document.querySelector(".market-status");

    if (!feed || !searchInput) {
        console.error("Market News JS: Required DOM elements not found");
        return;
    }

    let currentFilter = "ALL";
    let retryTimer = null;
    let retryCount = 0;

    const MAX_RETRIES = 5;
    const RETRY_DELAY = 2000;

    let autoRefreshTimer = null;
    const AUTO_REFRESH_INTERVAL = 60000; // 60 sec

    // =========================
    // MARKET STATUS CHECK
    // =========================
    function isMarketLive() {
        if (!marketStatusEl) return true;
        return marketStatusEl.innerText.toUpperCase().includes("LIVE");
    }

    // =========================
    // LOADING UI
    // =========================
    function showLoading() {
        feed.innerHTML = `<p style="color:#94a3b8;">Loading latest market news...</p>`;
    }

    // =========================
    // LOAD NEWS
    // =========================
    function loadNews(force = false) {

        if (retryTimer) {
            clearTimeout(retryTimer);
            retryTimer = null;
        }

        const query = searchInput.value || "";
        const url =
            `/api/market-news/?filter=${currentFilter}` +
            `&q=${encodeURIComponent(query)}` +
            `&refresh=${force ? 1 : 0}`;

        showLoading();

        fetch(url)
            .then(res => res.json())
            .then(data => {
                const news = data.news || [];

                if (news.length === 0 && retryCount < MAX_RETRIES) {
                    retryCount++;
                    retryTimer = setTimeout(() => loadNews(force), RETRY_DELAY);
                    return;
                }

                retryCount = 0;
                renderNews(news);
                updateSentiment(data.sentiment);
            })
            .catch(err => {
                console.error("Market News load error:", err);
            });
    }

    // =========================
    // RENDER NEWS
    // =========================
    function renderNews(news) {
        feed.innerHTML = "";

        if (!news.length) {
            feed.innerHTML = `<p style="color:#94a3b8;">No news found</p>`;
            return;
        }

        news.forEach(n => {
            const card = document.createElement("article");
            card.className = `news-card ${n.sentiment.toLowerCase()}`;

            card.innerHTML = `
                <div class="symbol">${n.symbol}</div>
                <div class="content">
                    <h2>${n.title}</h2>
                    <p class="meta">${n.source} · ${n.timestamp}</p>
                </div>
                <span class="tag ${n.sentiment.toLowerCase()}">${n.sentiment}</span>
            `;

            feed.appendChild(card);
        });
    }

    // =========================
    // UPDATE SENTIMENT
    // =========================
    function updateSentiment(s) {
        if (!s) return;

        document.querySelector(".sentiment-bar .bull").style.width = s.bullish + "%";
        document.querySelector(".sentiment-bar .bear").style.width = s.bearish + "%";
        document.querySelector(".sentiment-bar .neutral").style.width = s.neutral + "%";

        document.querySelector(".sentiment-labels").innerHTML = `
            <span class="bull">${s.bullish}% Bullish</span>
            <span class="bear">${s.bearish}% Bearish</span>
        `;
    }

    // =========================
    // 🔥 REFRESH BUTTON FIX
    // =========================
    if (refreshBtn) {
        refreshBtn.addEventListener("click", (e) => {
            e.preventDefault();
            retryCount = 0;
            loadNews(true); // 👈 FORCE REFRESH
        });
    }

    // =========================
    // FILTERS
    // =========================
    filterButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            currentFilter = btn.innerText.toUpperCase();
            if (currentFilter === "ALL NEWS") currentFilter = "ALL";

            retryCount = 0;
            loadNews(true);
            restartAutoRefresh();
        });
    });

    // =========================
    // SEARCH
    // =========================
    searchInput.addEventListener("input", () => {
        retryCount = 0;
        loadNews(true);
        restartAutoRefresh();
    });

    // =========================
    // AUTO REFRESH (MARKET AWARE)
    // =========================
    function startAutoRefresh() {
        if (!isMarketLive()) return;

        autoRefreshTimer = setInterval(() => {
            if (!isMarketLive()) {
                stopAutoRefresh();
                return;
            }
            loadNews();
        }, AUTO_REFRESH_INTERVAL);
    }

    function stopAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
            autoRefreshTimer = null;
        }
    }

    function restartAutoRefresh() {
        stopAutoRefresh();
        startAutoRefresh();
    }

    // =========================
    // INITIAL LOAD
    // =========================
    loadNews();
    startAutoRefresh();
});
