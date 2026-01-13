document.addEventListener("DOMContentLoaded", function () {

    const editBtn = document.getElementById("editProfileBtn");
    const editSection = document.getElementById("edit-profile-section");
    const cancelBtn = document.getElementById("cancelEdit");

    // Safety check
    if (!editBtn || !editSection) {
        console.warn("Profile JS: required elements not found");
        return;
    }

    // OPEN edit profile
    editBtn.addEventListener("click", function () {
        editSection.style.display = "block";
        editSection.scrollIntoView({ behavior: "smooth" });
    });

    // CANCEL edit profile
    if (cancelBtn) {
        cancelBtn.addEventListener("click", function () {
            editSection.style.display = "none";
        });
    }

});
