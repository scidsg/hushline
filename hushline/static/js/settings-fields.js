document.addEventListener("DOMContentLoaded", function () {
  const arrowClosed = "➤";
  const arrowOpen = "⮟";

  // All field forms start closed
  document
    .querySelectorAll(".field-form-content")
    .forEach(function (fieldContent) {
      fieldContent.style.display = "none";
    });
  document.querySelectorAll(".field-form-arrow").forEach(function (fieldArrow) {
    fieldArrow.textContent = arrowClosed;
  });

  // Toggle field forms
  document
    .querySelectorAll(".field-form-toggle")
    .forEach(function (fieldToggle) {
      fieldToggle.addEventListener("click", function () {
        const fieldContent = fieldToggle.parentElement.querySelector(
          ".field-form-content",
        );
        const fieldArrow = fieldToggle.querySelector(".field-form-arrow");

        if (fieldContent.style.display === "none") {
          fieldContent.style.display = "block";
          fieldArrow.textContent = arrowOpen;
        } else {
          fieldContent.style.display = "none";
          fieldArrow.textContent = arrowClosed;
        }
      });
    });

  // Hide choices when the field type is text or multiline_text
  function updateChoicesVisibility(fieldType) {
    const choicesContainer =
      fieldType.parentElement.parentElement.querySelector(`.choices-container`);
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

  // Hide required checkbox when the field type is multiple choice
  function updateRequiredVisibility(fieldType) {
    const requiredCheckboxContainer =
      fieldType.parentElement.parentElement.querySelector(
        `.required-checkbox-container`,
      );
    const requiredCheckbox =
      fieldType.parentElement.parentElement.querySelector(`.required-checkbox`);
    if (fieldType.value === "choice_multiple") {
      requiredCheckbox.checked = false;
      requiredCheckboxContainer.style.display = "none";
    } else {
      requiredCheckboxContainer.style.display = "block";
    }
  }
  document.querySelectorAll(".field-form").forEach(function (fieldForm) {
    const fieldType = fieldForm.querySelector(".field-type");
    updateRequiredVisibility(fieldType);
    fieldType.addEventListener("change", function () {
      updateRequiredVisibility(fieldType);
    });
  });

  // Add choice
  document.querySelectorAll(".add-choice").forEach(function (addButton) {
    addButton.addEventListener("click", function () {
      const fieldId = addButton.getAttribute("data-field-id");
      const choicesContainer = document.querySelector(
        `.choices-list-${fieldId}`,
      );

      // Calculate the new index based on the number of current choices
      const index = choicesContainer.children.length;
      const inputName = `choices-${index}-choice`;
      const inputId = `choices-${index}-choice`;

      const choiceItem = document.createElement("div");
      choiceItem.classList.add("choice-item");
      choiceItem.innerHTML = `
                <input type="text" name="${inputName}" id="${inputId}" />
                <button type="button" class="move-up-choice">↑</button>
                <button type="button" class="move-down-choice">↓</button>
                <button type="button" class="remove-choice">Remove</button>
            `;
      choicesContainer.appendChild(choiceItem);
      bindChoiceButtons(choiceItem);
      updateChoiceIndexes(choiceItem.parentNode);
    });
  });

  // Bind choice buttons (reuse function to handle dynamically added elements)
  function bindChoiceButtons(choiceItem) {
    const moveUpButton = choiceItem.querySelector(".move-up-choice");
    const moveDownButton = choiceItem.querySelector(".move-down-choice");
    const removeButton = choiceItem.querySelector(".remove-choice");

    moveUpButton.addEventListener("click", function () {
      const previous = choiceItem.previousElementSibling;
      if (previous) {
        choiceItem.parentNode.insertBefore(choiceItem, previous);
        updateChoiceIndexes(choiceItem.parentNode);
      }
    });

    moveDownButton.addEventListener("click", function () {
      const next = choiceItem.nextElementSibling;
      if (next) {
        choiceItem.parentNode.insertBefore(next, choiceItem);
        updateChoiceIndexes(choiceItem.parentNode);
      }
    });

    removeButton.addEventListener("click", function () {
      choiceItem.parentNode.removeChild(choiceItem);
      updateChoiceIndexes(choiceItem.parentNode);
    });
  }

  // Bind existing choice buttons
  document.querySelectorAll(".choice-item").forEach(function (choiceItem) {
    bindChoiceButtons(choiceItem);
  });

  // Update the indexes of choice items
  function updateChoiceIndexes(choicesContainer) {
    choicesContainer
      .querySelectorAll(".choice-item")
      .forEach(function (choiceItem, index) {
        const label = choiceItem.querySelector("label");
        const input = choiceItem.querySelector("input[type='text']");
        label.htmlFor = `choices-${index}-choice`;
        input.name = `choices-${index}-choice`;
        input.id = `choices-${index}-choice`;
      });
  }
  document
    .querySelectorAll(".choices-container")
    .forEach(function (choicesContainer) {
      updateChoiceIndexes(choicesContainer);
    });
});
