document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    const searchInput = document.getElementById('searchInput');
    const clearIcon = document.getElementById('clearIcon');
    let userData = []; // Will hold the user data loaded from JSON

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
        return text.replace(regex, '<span class="search-highlight">$1</span>');
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

                const userDiv = document.createElement('div');
                userDiv.className = 'user';
                userDiv.innerHTML = `
                    <h3>${displayNameHighlighted}</h3>
                    <p class="meta">@${usernameHighlighted}</p>
                    <div class="badgeContainer">${badgeContainer}</div>
                    ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ''}
                    <div class="user-actions">
                        <a href="/submit_message/${user.primary_username}">Send a Message</a>
                    </div>
                `;
                userListContainer.appendChild(userDiv);
            });
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

    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            const activeContent = document.getElementById(tab.getAttribute('data-tab'));
            activeContent.classList.add('active');

            handleSearchInput(); // Filter again when tab changes
            updatePlaceholder();
        });
    });

    searchInput.addEventListener('input', handleSearchInput);
    clearIcon.addEventListener('click', function () {
        searchInput.value = '';
        clearIcon.style.visibility = 'hidden';
        handleSearchInput();
    });

    loadData(); // Load the data when the page is ready
    updatePlaceholder(); // Initialize placeholder text
});
