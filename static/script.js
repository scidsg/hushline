document.addEventListener('DOMContentLoaded', function() {
    // Handle mobile navigation toggle
    const mobileNavButton = document.querySelector('.mobileNav');
    const navMenu = document.querySelector('header nav ul');
    
    mobileNavButton.addEventListener('click', function() {
        navMenu.classList.toggle('show');
    });

    // Handle account deletion confirmation
    const deleteButton = document.getElementById('deleteAccountButton');

    if (deleteButton) {
        deleteButton.addEventListener('click', function(event) {
            const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    }
});
