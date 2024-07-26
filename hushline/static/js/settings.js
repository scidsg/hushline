document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.tab');
    const tabPanels = document.querySelectorAll('.tab-content');
    const bioCountEl = document.querySelector('.bio-count');
    // Deletion account confirmation logic
    document.getElementById('deleteAccountButton')?.addEventListener('click', function(event) {
        const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
        if (!confirmed) {
            event.preventDefault();
        }
    });

    document.querySelector("input[name='show_in_directory']").addEventListener('change', function(e) {
        // time out to let animation finish
        setTimeout(() => {
            document.querySelector("button[name='update_directory_visibility']").click();
        }, 200)
    });

    document.getElementById('bio').addEventListener('keyup', function(e) {
        bioCountEl.textContent = e.target.value.length;
    });

    tabs.forEach(tab => {
        tab.addEventListener('click', function(e) {
            window.activateTab(e, tabs, tabPanels);
        });
        tab.addEventListener('keydown', function(e) {
            window.handleKeydown(e)
        });
    });
});
