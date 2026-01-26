(function () {
    const symbolsRaw = (window.mlJobsSymbols || "").trim();
    if (!symbolsRaw) {
        return;
    }

    const symbols = symbolsRaw.split(",").map(s => s.trim()).filter(Boolean);
    const priceCells = {};
    document.querySelectorAll(".price-cell[data-price]").forEach(cell => {
        const sym = cell.getAttribute("data-price");
        if (sym) {
            priceCells[sym] = cell;
        }
    });

    const chunkSize = 50;

    function formatPrice(value) {
        if (value === null || value === undefined) {
            return "--";
        }
        const num = Number(value);
        if (Number.isNaN(num)) {
            return "--";
        }
        return num.toFixed(2);
    }

    function fetchBatch(batch) {
        const url = `/api/v1/quotes?symbols=${encodeURIComponent(batch.join(","))}`;
        return fetch(url)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (!data || !Array.isArray(data.quotes)) {
                    return;
                }
                data.quotes.forEach(item => {
                    const sym = item.symbol;
                    const cell = priceCells[sym];
                    if (!cell) {
                        return;
                    }
                    const price = formatPrice(item.current_price);
                    cell.textContent = price === "--" ? "--" : `Rs ${price}`;
                });
            })
            .catch(() => {});
    }

    function refreshPrices() {
        const batches = [];
        for (let i = 0; i < symbols.length; i += chunkSize) {
            batches.push(symbols.slice(i, i + chunkSize));
        }
        batches.reduce((p, batch) => p.then(() => fetchBatch(batch)), Promise.resolve());
    }

    refreshPrices();
    setInterval(refreshPrices, 10000);
})();
