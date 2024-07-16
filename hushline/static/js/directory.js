document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    const searchInput = document.getElementById('searchInput');
    const clearIcon = document.getElementById('clearIcon');
    let userData = []; // Will hold the user data loaded from JSON
    let isSessionUser = false

    function updatePlaceholder() {
        const activeTab = document.querySelector('.tab.active').getAttribute('data-tab');
        searchInput.placeholder = `Search ${activeTab === 'verified' ? 'verified ' : ''}users...`;
    }

    function searchUsers() {
        const query = searchInput.value.trim().toLowerCase();
        const tab = document.querySelector('.tab.active').getAttribute('data-tab');
        const filteredUsers = userData.filter(user => {
            const userText = `${user.primary_username} ${user.display_name || ''} ${user.bio || ''}`.toLowerCase();
            return userText.includes(query) && (tab === 'all' || (user.is_verified && tab === 'verified'));
        });
        updateUsersList(filteredUsers);
    }

    function loadData() {
        fetch('/directory/users.json')
            .then(response => response.json())
            .then(data => {
                userData = data;
                handleSearchInput(); // Initial display after data is loaded
            })
            .catch(error => console.error('Failed to load user data:', error));
    }

    async function checkIfSessionUser() {
        const response = await fetch('/directory/get-session-user.json');
        const {logged_in} = await response.json();
        isSessionUser = logged_in;
    }

    function filterUsers(query) {
        const tab = document.querySelector('.tab.active').getAttribute('data-tab');
        return userData.filter(user => {
            const searchText = `${user.primary_username} ${user.display_name} ${user.bio}`.toLowerCase();
            const matchesTab = tab === 'all' || (tab === 'verified' && user.is_verified);
            return searchText.includes(query.toLowerCase()) && matchesTab;
        });
    }

    function highlightMatch(text, query) {
        if (!query) return text; // If no query, return the text unmodified
        const regex = new RegExp(`(${query})`, 'gi'); // Case-insensitive matching
        return text.replace(regex, '<mark class="search-highlight">$1</mark>');
    }


    function reportUser(username, bio) {

        // Construct the message content with explicit line breaks
        const messageContent = `Reported user: ${username}\n\nBio: ${bio}\n\nReason:`;

        // Encode the message content to ensure line breaks and other special characters are correctly handled
        const encodedMessage = encodeURIComponent(messageContent);
        
        // Redirect to the message submission form for the admin with the pre-filled content
        const submissionUrl = `/submit_message/admin?prefill=${encodedMessage}`;
        window.location.href = submissionUrl;
    }

    function displayUsers(users, query) {
        const userListContainer = document.querySelector('.tab-content.active .user-list');
        const activeTab = document.querySelector('.tab.active').getAttribute('data-tab');
        userListContainer.innerHTML = '';

        if (users.length > 0) {
            users.forEach(user => {
                const displayNameHighlighted = highlightMatch(user.display_name || user.primary_username, query);
                const usernameHighlighted = highlightMatch(user.primary_username, query);
                const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : '';

                let badgeContainer = '';

                if (user.is_admin) {
                    badgeContainer += '<p class="badge">⚙️ Admin</p>';
                }

                // Only include the "Verified" badge if the "all" tab is active
                if (activeTab === 'all' && user.is_verified) {
                    badgeContainer += '<p class="badge">⭐️ Verified Account</p>';
                }

                
                const userDiv = document.createElement('article');
                userDiv.className = 'user';
                userDiv.setAttribute('aria-label', `User ${user.display_name || user.primary_username}`);
                userDiv.innerHTML = `
                    <h3>${displayNameHighlighted}</h3>
                    <p class="meta">@${usernameHighlighted}</p>
                    <div class="badgeContainer">${badgeContainer}</div>
                    ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ''}
                    <div class="user-actions">
                        <a href="/submit_message/${user.primary_username}">Send a Message</a>
                        ${isSessionUser ? `<a href="#" class="report-link" data-username="${user.primary_username}" data-display-name="${user.display_name || user.primary_username }" data-bio="${user.bio ?? "No bio"}">Report Account</a>` : ``}
                    </div>
                `;
                userListContainer.appendChild(userDiv);
            });

            createReportEventListeners('.tab-content.active .user-list');
        } else {
            userListContainer.innerHTML = '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>';
        }
    }

    function handleSearchInput() {
        const query = searchInput.value.trim();
        const filteredUsers = filterUsers(query);
        displayUsers(filteredUsers, query);
        clearIcon.style.visibility = query.length ? 'visible' : 'hidden';
    }

    function activateTab(event) {    
        const selectedTab = event.target;
        const targetPanel = document.getElementById(selectedTab.getAttribute('aria-controls'));

        // Deselect all tabs and hide all panels
        tabs.forEach(tab => {
            tab.setAttribute('aria-selected', 'false');
            tab.classList.remove('active');
            document.getElementById(tab.getAttribute('aria-controls')).hidden = true;
        });

        // Select the clicked tab and show the corresponding panel
        selectedTab.setAttribute('aria-selected', 'true');
        selectedTab.classList.add('active');
        targetPanel.hidden = false;

        handleSearchInput(); // Filter again when tab changes
        updatePlaceholder();
        
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
    
    searchInput.addEventListener('input', handleSearchInput);
    clearIcon.addEventListener('click', function () {
        searchInput.value = '';
        clearIcon.style.visibility = 'hidden';
        // put focus back on input after clear button is invoked
        document.getElementById("searchInput").focus();
        handleSearchInput();
    });



    function createReportEventListeners(selector) {
        document.querySelector(selector).addEventListener('click', function(event) {
            if (event.target.classList.contains('report-link')) {
                event.preventDefault();
                const link = event.target;
                const username = link.getAttribute('data-username');
                const bio = link.getAttribute('data-bio');
                reportUser(username, bio);
            }
        });
    }
    checkIfSessionUser()
    updatePlaceholder(); // Initialize placeholder text
    loadData();
});