document.addEventListener("DOMContentLoaded", function () {
  const button = document.getElementById("copy-link-button");
  if (!button) {
    console.debug('No button');
    return
  }

  const target = document.getElementById(button.dataset.target);
  if (!target) {
    console.debug('No target');
    return
  }

  button.onclick = () => {
    const data = new ClipboardItem({
      "text/plain": Promise.resolve(new Blob([target.innerText], { type: "text/plain" })),
    }); 

    navigator.clipboard.write([data]).then(function() {
      console.debug("Address copied");
    }, function() {
      console.error("Address could not be copied to the clipboard");
    });

    return false;
  };
});
