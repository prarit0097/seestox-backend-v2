document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("stock-search-input");
    const analyzeBtn = document.getElementById("analyze-btn");

    if (!input || !analyzeBtn) return;

    function goToIndex() {
        const company = input.value.trim();
        if (!company) return;

        // ✅ INDEX VIEW (NOT dashboard)
        window.location.href = `/stock-detail/?company=${encodeURIComponent(company)}`;
    }

    analyzeBtn.addEventListener("click", goToIndex);

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            goToIndex();
        }
    });

});

document.addEventListener("DOMContentLoaded", () => {
    const searchBox = document.querySelector(".stock-search-box");
    const input = document.getElementById("stock-search-input");

    if (searchBox && input) {
        searchBox.addEventListener("click", () => {
            input.focus();
        });
    }
});