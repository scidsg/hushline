document.addEventListener('DOMContentLoaded', function() {
    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const bioCountEl = document.querySelector('.bio-count');

    function activateTab(event) {
        const selectedTab = event.target;
        const targetPanel = document.getElementById(selectedTab.getAttribute('aria-controls'));
    
        // Deselect all tabs and hide all panels
        tabs.forEach(tab => {
            tab.setAttribute('aria-selected', 'false');
            tab.classList.remove('active');
            const panel = document.getElementById(tab.getAttribute('aria-controls'));
            panel.hidden = true;
            panel.style.display = 'none';
        });
    
        // Select the clicked tab and show the corresponding panel
        selectedTab.setAttribute('aria-selected', 'true');
        selectedTab.classList.add('active');
        targetPanel.hidden = false;
        targetPanel.style.display = 'block';
    }
    
    function handleKeydown(event) {
        const { key } = event;
        const currentTab = event.target;
        let newTab;
    
        switch (key) {
            case 'ArrowLeft':
                newTab = currentTab.parentElement.previousElementSibling?.querySelector('.tab');
                break;
            case 'ArrowRight':
                newTab = currentTab.parentElement.nextElementSibling?.querySelector('.tab');
                break;
            case 'Home':
                newTab = tabs[0];
                break;
            case 'End':
                newTab = tabs[tabs.length - 1];
                break;
            default:
                return;
        }
    
        if (newTab) {
            newTab.focus();
            newTab.click();
            event.preventDefault();
        }
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', activateTab);
        tab.addEventListener('keydown', handleKeydown);
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

    document.querySelector("input[name='show_in_directory']").addEventListener('change', function(e) {
        // time out to let animation finish
        setTimeout(() => {
            document.querySelector("button[name='update_directory_visibility']").click();
        }, 200)
    });

    document.getElementById('bio').addEventListener('keyup', function(e) {
        bioCountEl.textContent = e.target.value.length;
    });
});
