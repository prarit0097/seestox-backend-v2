// static/js/stock_search/search.js
// STOCK SEARCH — AUTOCOMPLETE + KEYBOARD (NEW PAGE)

document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("stock-search-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const suggestionBox = document.getElementById("search-suggestions");

    let suggestions = [];
    let activeIndex = -1;
    let debounceTimer = null;

    if (!input || !suggestionBox) return;

    // -----------------------------
    // FETCH SUGGESTIONS
    // -----------------------------
    async function fetchSuggestions(query) {
        const res = await fetch(`/search-suggestions/?q=${encodeURIComponent(query)}`);
        return await res.json();
    }

    // -----------------------------
    // RENDER SUGGESTIONS
    // -----------------------------
    function renderSuggestions(list) {
        suggestionBox.innerHTML = "";
        suggestions = list;
        activeIndex = -1;

        if (!list || list.length === 0) {
            suggestionBox.innerHTML = `
                <div class="suggestion-item muted">
                    No matching company found
                </div>`;
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
            div.addEventListener("click", () => selectSuggestion(index));

            suggestionBox.appendChild(div);
        });

        suggestionBox.classList.remove("hidden");
    }

    // -----------------------------
    // ACTIVE ITEM
    // -----------------------------
    function setActive(index) {
        const items = suggestionBox.querySelectorAll(".suggestion-item");
        items.forEach(el => el.classList.remove("active"));

        if (items[index]) {
            items[index].classList.add("active");
            activeIndex = index;
        }
    }

    // -----------------------------
    // SELECT
    // -----------------------------
    function selectSuggestion(index) {
        if (!suggestions[index]) return;
        input.value = suggestions[index].symbol;
        hideSuggestions();
    }

    // -----------------------------
    // HIDE
    // -----------------------------
    function hideSuggestions() {
        suggestionBox.classList.add("hidden");
        activeIndex = -1;
    }

    // -----------------------------
    // INPUT EVENT
    // -----------------------------
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

    // -----------------------------
    // KEYBOARD
    // -----------------------------
    input.addEventListener("keydown", (e) => {

        if (suggestionBox.classList.contains("hidden")) return;

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
            if (activeIndex >= 0) {
                selectSuggestion(activeIndex);
            }
        }

        if (e.key === "Escape") {
            hideSuggestions();
        }
    });

    // -----------------------------
    // CLICK OUTSIDE
    // -----------------------------
    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !suggestionBox.contains(e.target)) {
            hideSuggestions();
        }
    });

});
