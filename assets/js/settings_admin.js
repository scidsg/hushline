document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelectorAll("form[data-auto-submit-select='true']")
    .forEach(function (form) {
      const select = form.querySelector("select[name='account_category']");
      if (!select) {
        return;
      }

      select.addEventListener("change", function () {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
          return;
        }
        form.submit();
      });
    });
});
