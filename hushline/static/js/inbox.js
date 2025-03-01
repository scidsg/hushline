document.addEventListener("DOMContentLoaded", function () {
  // Listen for clicks anywhere in the document
  document.addEventListener("click", function (event) {
    // Check if the clicked element or its parents have the 'btn-danger' class
    let targetElement = event.target;
    while (targetElement != null) {
      if (
        targetElement.classList &&
        targetElement.classList.contains("btn-danger")
      ) {
        // Confirm before deletion
        const confirmed = confirm(
          "Are you sure you want to delete this message? This cannot be undone.",
        );
        if (!confirmed) {
          event.preventDefault();
        }
        return; // Exit the loop and function after handling the click
      }
      targetElement = targetElement.parentElement;
    }
  });
});

document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab");
  const tabList = document.querySelectorAll(".tab-list .tab");
  const mainElement = document.querySelector("main");

  if (tabList.length >= 5) {
    mainElement.classList.add("inbox-main");
  }
});
