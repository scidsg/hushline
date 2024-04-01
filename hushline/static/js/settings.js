document.addEventListener('DOMContentLoaded', function() {
    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    function removeActiveClasses() {
        tabs.forEach(tab => tab.classList.remove('active'));
        tabContents.forEach(content => content.style.display = 'none');
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            removeActiveClasses();
            this.classList.add('active');
            const activeTabContent = document.getElementById(this.getAttribute('data-tab'));
            if (activeTabContent) {
                activeTabContent.style.display = 'block';
            }
        });
    });

    if (tabs.length > 0) {
        tabs[0].click(); // Open the first tab automatically
    }

    // Deletion account confirmation logic
    document.getElementById('deleteAccountButton')?.addEventListener('click', function(event) {
        const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
        if (!confirmed) {
            event.preventDefault();
        }
    });
});
