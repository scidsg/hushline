document.addEventListener("DOMContentLoaded", function () {
    const arrowClosed = '➤';
    const arrowOpen = '⮟';

    // All field forms start closed
    document.querySelectorAll(".field-form-content").forEach(function (fieldContent) {
        fieldContent.style.display = "none";
    });
    document.querySelectorAll(".field-form-arrow").forEach(function (fieldArrow) {
        fieldArrow.textContent = arrowClosed;
    });

    // Toggle field forms
    document.querySelectorAll(".field-form-toggle").forEach(function (fieldToggle) {
        fieldToggle.addEventListener("click", function () {
            const fieldContent = fieldToggle.parentElement.querySelector(".field-form-content");
            const fieldArrow = fieldToggle.querySelector(".field-form-arrow");

            if (fieldContent.style.display === "none") {
                fieldContent.style.display = "block";
                fieldArrow.textContent = arrowOpen;
            } else {
                fieldContent.style.display = "none";
                fieldArrow.textContent = arrowClosed;
            };
        });
    });

    // Hide choices when the field type is text or multiline_text
    function updateChoicesVisibility(fieldType) {
        const choicesContainer = fieldType.parentElement.parentElement.querySelector(`.choices-container`);
        if (fieldType.value === "text" || fieldType.value === "multiline_text") {
            choicesContainer.style.display = "none";
        } else {
            choicesContainer.style.display = "block";
        }
    }
    document.querySelectorAll(".field-form").forEach(function (fieldForm) {
        const fieldType = fieldForm.querySelector(".field-type");
        updateChoicesVisibility(fieldType);
        fieldType.addEventListener("change", function () {
            updateChoicesVisibility(fieldType);
        });
    });
});
