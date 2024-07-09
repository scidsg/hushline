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

    // Run the function to correct double periods
    correctDoublePeriods();
});