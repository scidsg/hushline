document.addEventListener("DOMContentLoaded", function () {
  const bioField = document.getElementById("bio");
  const bioCountEl = document.querySelector(".bio-count");
  if (!bioField || !bioCountEl) {
    return;
  }

  const updateCount = () => {
    bioCountEl.textContent = String(bioField.value.length);
  };

  updateCount();
  bioField.addEventListener("input", updateCount);
});
