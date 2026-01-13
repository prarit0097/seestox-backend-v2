const RECENT_KEY = "recent_stocks";

function saveRecent(symbol) {
    let list = JSON.parse(localStorage.getItem(RECENT_KEY)) || [];
    list = list.filter(s => s !== symbol);
    list.unshift(symbol);
    list = list.slice(0, 5);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
}

function loadRecent() {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY)) || [];
    const box = document.getElementById("recent");
    if (!list.length) return;

    box.innerHTML = list.map(s => `
        <span class="recent-item">${s}</span>
    `).join("");
}

document.addEventListener("click", e => {
    if (e.target.classList.contains("recent-item")) {
        document.getElementById("stock-input").value = e.target.innerText;
    }
});
