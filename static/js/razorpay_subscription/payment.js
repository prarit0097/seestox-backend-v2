async function startPayment(plan) {
    try {
        // 1️⃣ Create order
        const res = await fetch("/create-order/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify({ plan }),
        });
        const data = await res.json();

        if (!data.order_id) {
            alert("Unable to start payment");
            return;
        }

        // 2️⃣ Razorpay options
        const options = {
            key: data.key,
            amount: data.amount,
            currency: "INR",
            name: "AIStockTool",
            description: `${plan} Subscription`,
            order_id: data.order_id,

            handler: async function (response) {
                // 3️⃣ VERIFY PAYMENT (MOST IMPORTANT)
                const formData = new FormData();
                formData.append("razorpay_order_id", response.razorpay_order_id);
                formData.append("razorpay_payment_id", response.razorpay_payment_id);
                formData.append("razorpay_signature", response.razorpay_signature);
                formData.append("plan", plan);

                const verifyRes = await fetch("/verify-payment/", {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-CSRFToken": getCookie("csrftoken"),
                    },
                });

                const verifyData = await verifyRes.json();

                if (verifyData.status === "success") {
                    alert("✅ Plan Activated Successfully");
                    window.location.reload(); // 🔥 UI refresh
                } else {
                    alert("❌ Payment verification failed");
                }
            },

            theme: {
                color: "#22c55e",
            },
        };

        // 4️⃣ Open Razorpay
        const rzp = new Razorpay(options);
        rzp.open();

    } catch (err) {
        console.error(err);
        alert("Payment error");
    }
}

// CSRF helper
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
