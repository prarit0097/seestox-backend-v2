const input = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const messages = document.getElementById("messages");
const chatArea = document.getElementById("chat-area");
const searchArea = document.getElementById("chat-search-area");
const chips = document.querySelectorAll(".chip");

function addMessage(text, type) {
    const div = document.createElement("div");
    div.className = `msg ${type}`;
    div.innerText = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

async function sendMessage(text) {
    if (!text.trim()) return;

    // Move search to top (UNCHANGED)
    searchArea.classList.remove("center");
    searchArea.classList.add("top");
    chatArea.classList.remove("hidden");

    addMessage(text, "user");
    input.value = "";

    // Thinking indicator (UNCHANGED UX)
    const thinking = document.createElement("div");
    thinking.className = "msg ai thinking";
    thinking.innerText = "Thinking...";
    messages.appendChild(thinking);
    messages.scrollTop = messages.scrollHeight;

    try {
        const response = await fetch("/api/chat/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify({
                message: text
            })
        });

        const data = await response.json();

        thinking.remove();
        addMessage(data.reply || "⚠️ No response from AI.", "ai");

    } catch (error) {
        thinking.remove();
        addMessage(
            "⚠️ Unable to reach AI engine. Please try again.",
            "ai"
        );
    }
}

sendBtn.addEventListener("click", () => {
    sendMessage(input.value);
});

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        sendMessage(input.value);
    }
});

chips.forEach(chip => {
    chip.addEventListener("click", () => {
        sendMessage(chip.innerText);
    });
});

function getCSRFToken() {
    const token = document.cookie
        .split("; ")
        .find(row => row.startsWith("csrftoken="));
    if (token) return token.split("=")[1];

    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
}
