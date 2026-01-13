// =====================================
// WATCHLIST PRICE UPDATES (AS IS)
// =====================================
async function updateWatchlistPrices() {
    try {
        const res = await fetch("/watchlist/data/");
        const data = await res.json();

        if (!data || !data.watchlist) return;

        data.watchlist.forEach(item => {
            const priceEl = document.getElementById(`price-${item.symbol}`);
            if (!priceEl) return;

            if (item.current_price !== null && item.current_price !== undefined) {
                priceEl.textContent = "₹" + item.current_price;
            }
        });

    } catch (e) {
        console.error("Price update failed", e);
    }
}

setInterval(updateWatchlistPrices, 3000);
updateWatchlistPrices();


// =====================================
// WATCHLIST SEARCH + AUTOCOMPLETE
// =====================================
document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("watchlist-search-input");
    const suggestionBox = document.getElementById("watchlist-search-suggestions");
    const addBtn = document.getElementById("watchlist-add-btn");

    if (!input || !suggestionBox || !addBtn) return;

    let suggestions = [];
    let activeIndex = -1;
    let debounceTimer = null;

    async function fetchSuggestions(query) {
        const res = await fetch(`/search-suggestions/?q=${encodeURIComponent(query)}`);
        return await res.json();
    }

    function renderSuggestions(list) {
        suggestionBox.innerHTML = "";
        suggestions = list;
        activeIndex = -1;

        if (!list || list.length === 0) {
            suggestionBox.innerHTML = `<div class="suggestion-item muted">No match found</div>`;
            suggestionBox.classList.remove("hidden");
            return;
        }

        list.forEach((item, index) => {
            const div = document.createElement("div");
            div.className = "suggestion-item";
            div.innerHTML = `<strong>${item.symbol}</strong><div>${item.company}</div>`;

            div.addEventListener("mouseenter", () => setActive(index));
            div.addEventListener("click", () => selectSuggestion(index));

            suggestionBox.appendChild(div);
        });

        suggestionBox.classList.remove("hidden");
    }

    function setActive(index) {
        const items = suggestionBox.querySelectorAll(".suggestion-item");
        items.forEach(el => el.classList.remove("active"));
        if (items[index]) {
            items[index].classList.add("active");
            activeIndex = index;
        }
    }

    function selectSuggestion(index) {
        if (!suggestions[index]) return;
        input.value = suggestions[index].symbol;
        hideSuggestions();
    }

    function hideSuggestions() {
        suggestionBox.classList.add("hidden");
        activeIndex = -1;
    }

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

    input.addEventListener("keydown", (e) => {
        const items = suggestionBox.querySelectorAll(".suggestion-item");
        if (!items.length) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((activeIndex + 1) % items.length);
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((activeIndex - 1 + items.length) % items.length);
        }

        if (e.key === "Enter") {
            e.preventDefault();
            if (activeIndex >= 0) selectSuggestion(activeIndex);
        }

        if (e.key === "Escape") hideSuggestions();
    });

    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !suggestionBox.contains(e.target)) {
            hideSuggestions();
        }
    });

    // =====================================
    // ADD TO WATCHLIST
    // =====================================
    addBtn.addEventListener("click", async () => {
        const symbol = input.value.trim().toUpperCase();
        if (!symbol) return;

        const formData = new FormData();
        formData.append("symbol", symbol);

        const res = await fetch("/watchlist/add/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken()
            },
            body: formData
        });

        if (res.ok) {
            location.reload(); // simplest & safe
        }
    });
});


// =====================================
// REMOVE FROM WATCHLIST (AS IS)
// =====================================
document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".remove-btn");
    if (!btn) return;

    const card = btn.closest(".watchlist-card");
    if (!card) return;

    const symbol = card.dataset.symbol;
    if (!symbol) return;

    try {
        const res = await fetch("/watchlist/remove/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify({ symbol })
        });

        if (res.ok) card.remove();

    } catch (err) {
        console.error("Remove error", err);
    }
});

// =====================================
// 🔗 CLICK CARD → STOCK DETAIL PAGE
// =====================================
document.addEventListener("click", (e) => {

    // ❌ ignore remove button click
    if (e.target.closest(".remove-btn")) return;

    const card = e.target.closest(".watchlist-card");
    if (!card) return;

    const symbol = card.dataset.symbol;
    if (!symbol) return;

    // 🔁 redirect to stock detail page
    window.location.href = `/stock-detail/?company=${symbol}`;
});


// =====================================
// CSRF TOKEN
// =====================================
function getCSRFToken() {
    return document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="))
        ?.split("=")[1];
}
