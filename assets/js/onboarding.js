document.addEventListener("DOMContentLoaded", function () {
  const bio = document.getElementById("bio");
  const bioCountEl = document.querySelector(".bio-count");

  if (!bio || !bioCountEl) {
    return;
  }

  const updateCount = () => {
    bioCountEl.textContent = String(bio.value.length);
  };

  updateCount();
  bio.addEventListener("input", updateCount);
});
