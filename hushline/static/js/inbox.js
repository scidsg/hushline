document.addEventListener('DOMContentLoaded', function() {
    // Handle message deletion confirmation
    document.querySelectorAll('.deleteMessageButton').forEach(button => {
        button.addEventListener('click', function(event) {
            const confirmed = confirm('Are you sure you want to delete this message? This cannot be undone.');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });
});
