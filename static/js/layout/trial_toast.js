document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".nav.disabled, .nav-primary.disabled").forEach(item => {
        item.addEventListener("click", function () {
            showTrialToast();
        });
    });
});

function showTrialToast() {
    let toast = document.createElement("div");
    toast.className = "trial-toast";
    toast.innerText = "Your trial has ended. Upgrade to continue.";

    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add("show"), 50);

    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
