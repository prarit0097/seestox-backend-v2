// static/js/stock_search/stock_detail_redirect.js
// STOCK SEARCH → STOCK DETAIL PAGE (FINAL & CLEAN VERSION)

document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("stock-search-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const suggestionBox = document.getElementById("search-suggestions");

    // Hard safety check
    if (!input || !analyzeBtn || !suggestionBox) {
        console.warn("Stock search elements missing");
        return;
    }

    // =============================
    // STATE
    // =============================
    let suggestions = [];
    let activeIndex = -1;
    let debounceTimer = null;

    // =============================
    // 🔍 FETCH SUGGESTIONS
    // =============================
    async function fetchSuggestions(query) {
        try {
            const res = await fetch(
                `/search-suggestions/?q=${encodeURIComponent(query)}`
            );
            return await res.json();
        } catch (err) {
            console.error("Suggestion fetch failed", err);
            return [];
        }
    }

    // =============================
    // 🚀 FINAL REDIRECT (ONLY ONE)
    // =============================
    function goToStockDetail(symbol) {
        if (!symbol) return;

        // ✅ FINAL PAGE (NO index.html ANYWHERE)
        window.location.href =
            `/stock-detail/?company=${encodeURIComponent(symbol)}`;
    }

    // =============================
    // 📋 RENDER SUGGESTIONS
    // =============================
    function renderSuggestions(list) {
        suggestionBox.innerHTML = "";
        suggestions = list;
        activeIndex = -1;

        if (!list || list.length === 0) {
            suggestionBox.innerHTML = `
                <div class="suggestion-item muted">
                    No matching company found
                </div>
            `;
            suggestionBox.classList.remove("hidden");
            return;
        }

        list.forEach((item, index) => {
            const div = document.createElement("div");
            div.className = "suggestion-item";
            div.dataset.index = index;

            div.innerHTML = `
                <strong>${item.symbol}</strong>
                <div class="company-name">${item.company}</div>
            `;

            div.addEventListener("mouseenter", () => setActive(index));

            div.addEventListener("click", () => {
                input.value = item.symbol;
                hideSuggestions();
                goToStockDetail(item.symbol);
            });

            suggestionBox.appendChild(div);
        });

        suggestionBox.classList.remove("hidden");
    }

    // =============================
    // 🔵 ACTIVE HIGHLIGHT
    // =============================
    function setActive(index) {
        const items = suggestionBox.querySelectorAll(".suggestion-item");
        items.forEach(el => el.classList.remove("active"));

        if (items[index]) {
            items[index].classList.add("active");
            activeIndex = index;
        }
    }

    // =============================
    // ❌ HIDE SUGGESTIONS
    // =============================
    function hideSuggestions() {
        suggestionBox.classList.add("hidden");
        activeIndex = -1;
    }

    // =============================
    // ⌨️ INPUT (AUTOCOMPLETE)
    // =============================
    input.addEventListener("input", () => {
        const query = input.value.trim();
        clearTimeout(debounceTimer);

        if (query.length < 2) {
            hideSuggestions();
            return;
        }

        debounceTimer = setTimeout(async () => {
            const data = await fetchSuggestions(query);
            renderSuggestions(data);
        }, 250);
    });

    // =============================
    // ⌨️ KEYBOARD NAVIGATION
    // =============================
    input.addEventListener("keydown", (e) => {
        const items = suggestionBox.querySelectorAll(".suggestion-item");

        if (e.key === "ArrowDown" && items.length) {
            e.preventDefault();
            setActive((activeIndex + 1) % items.length);
        }

        if (e.key === "ArrowUp" && items.length) {
            e.preventDefault();
            setActive((activeIndex - 1 + items.length) % items.length);
        }

        if (e.key === "Enter") {
            e.preventDefault();

            // Selected suggestion
            if (activeIndex >= 0 && suggestions[activeIndex]) {
                goToStockDetail(suggestions[activeIndex].symbol);
            }
            // Manual input
            else {
                goToStockDetail(input.value.trim());
            }
        }

        if (e.key === "Escape") {
            hideSuggestions();
        }
    });

    // =============================
    // 🖱️ ANALYZE BUTTON
    // =============================
    analyzeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        goToStockDetail(input.value.trim());
    });

    // =============================
    // 🖱️ CLICK OUTSIDE
    // =============================
    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !suggestionBox.contains(e.target)) {
            hideSuggestions();
        }
    });

});
