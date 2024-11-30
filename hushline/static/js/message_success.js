document.addEventListener("DOMContentLoaded", function () {
  const button = document.getElementById("copy-link-button");
  if (!button) return;

  const target = document.getElementById(button.dataset.target);
  const successMessage = document.getElementById("copy-link-success");

  if (!target || !successMessage) return;

  button.onclick = () => {
    const textToCopy = target.innerText;
    navigator.clipboard.writeText(textToCopy).then(
      () => {
        successMessage.classList.add("show");

        setTimeout(() => {
          successMessage.classList.remove("show");
        }, 3000);
      },
      () => {},
    );

    return false;
  };
});
