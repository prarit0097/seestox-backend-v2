// static/js/search.js
// PHASE-1 STEP-2 — AUTOCOMPLETE + KEYBOARD (STABLE VERSION)

document.addEventListener("DOMContentLoaded", () => {

    // -------- ELEMENTS --------
    const input = document.getElementById("stock-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const suggestionBox = document.getElementById("suggestion-box");

    // -------- STATE --------
    let suggestions = [];
    let activeIndex = -1;
    let debounceTimer = null;

    // -------- BASIC STYLES (JS controlled, CSS later) --------
    suggestionBox.style.position = "absolute";
    suggestionBox.style.width = "100%";
    suggestionBox.style.zIndex = "1000";
    suggestionBox.style.display = "none";

    // -------- FETCH SUGGESTIONS --------
    async function fetchSuggestions(query) {
        const res = await fetch(`/search-suggestions/?q=${query}`);
        return await res.json();
    }

    // -------- RENDER --------
    function renderSuggestions(list) {
        suggestionBox.innerHTML = "";
        suggestions = list;
        activeIndex = -1;

        if (!list || list.length === 0) {
            suggestionBox.innerHTML = `
                <div class="suggestion-item no-result">
                    No company found
                </div>`;
            suggestionBox.style.display = "block";
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

        suggestionBox.style.display = "block";
    }

    // -------- ACTIVE HIGHLIGHT --------
    function setActive(index) {
        const items = suggestionBox.querySelectorAll(".suggestion-item");

        items.forEach(el => el.classList.remove("active"));

        if (items[index]) {
            items[index].classList.add("active");
            activeIndex = index;
        }
    }

    // -------- SELECT --------
    function selectSuggestion(index) {
        if (!suggestions[index]) return;

        input.value = suggestions[index].symbol;
        hideSuggestions();
        analyzeBtn.click();
    }

    // -------- HIDE --------
    function hideSuggestions() {
        suggestionBox.style.display = "none";
        activeIndex = -1;
    }

    // -------- INPUT EVENT --------
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

    // -------- KEYBOARD --------
    input.addEventListener("keydown", (e) => {

        if (suggestionBox.style.display === "none") return;

        const items = suggestionBox.querySelectorAll(".suggestion-item");
        if (!items.length) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            let next = activeIndex + 1;
            if (next >= items.length) next = 0;
            setActive(next);
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            let prev = activeIndex - 1;
            if (prev < 0) prev = items.length - 1;
            setActive(prev);
        }

        if (e.key === "Enter") {
            e.preventDefault();
            if (activeIndex >= 0) {
                selectSuggestion(activeIndex);
            } else {
                hideSuggestions();
                analyzeBtn.click();
            }
        }

        if (e.key === "Escape") {
            hideSuggestions();
        }
    });

    // -------- CLICK OUTSIDE --------
    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !suggestionBox.contains(e.target)) {
            hideSuggestions();
        }
    });

});
