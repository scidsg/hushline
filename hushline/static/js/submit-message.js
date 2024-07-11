document.addEventListener("DOMContentLoaded", function() {
    // Function to correct double periods at the end of sentences
    function correctDoublePeriods() {
        let elements = document.querySelectorAll('.helper');
        elements.forEach(element => {
            let text = element.innerHTML;
            // Replace double periods at the end of sentences with a single period
            text = text.replace(/\.{2,}/g, '.');
            element.innerHTML = text;
        });
    }

    function prefillMessage() {
      // get the query param value from the URL to set as textarea value
      const urlParams = new URLSearchParams(window.location.search);
      const prefill = urlParams.get('prefill');
      const textarea = document.getElementById('content');
      if (prefill) {
        textarea.value = prefill;
      }
    }
    // Run the function to correct double periods
    correctDoublePeriods();
    prefillMessage();
});