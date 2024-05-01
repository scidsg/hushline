document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    const searchInput = document.getElementById('searchInput');
    const clearIcon = document.getElementById('clearIcon');

    function updatePlaceholder() {
        const activeTab = document.querySelector('.tab.active').getAttribute('data-tab');
        searchInput.placeholder = `Search ${activeTab === 'verified' ? 'verified ' : ''}users...`; // Update placeholder dynamically
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            document.querySelector('#' + tab.getAttribute('data-tab')).classList.add('active');

            updatePlaceholder();
            clearSearch(); // Clear the input and reset the list when changing tabs
        });
    });

    searchInput.addEventListener('input', function () {
        searchUsers(); // Trigger search on input
        clearIcon.style.visibility = this.value ? 'visible' : 'hidden'; // Show clear icon if there's text
    });

    clearIcon.addEventListener('click', function () {
        clearSearch();
        searchInput.focus(); // Focus on the search input after clearing
    });

    window.searchUsers = function() {
        const query = searchInput.value.trim();
        const tab = document.querySelector('.tab.active').getAttribute('data-tab');
        fetch(`/directory/search?query=${query}&tab=${tab}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(users => {
                console.log('Fetched users:', users);  // Log fetched users to see what we get
                updateUsersList(users);
            })
            .catch(error => {
                console.error('Error fetching users:', error);
                document.querySelector('.user-list').innerHTML = `<p class="error">Error fetching users: ${error.message}</p>`;
            });
    };

    function updateUsersList(users) {
        const userList = document.querySelector('.tab-content.active .user-list');
        console.log('Clearing user list and updating with new data...'); // Debug
        userList.innerHTML = ''; // Clear the list before adding new entries
        console.log('User list cleared.');
        if (users && users.length > 0) {
            users.forEach(user => {
                const userDiv = document.createElement('div');
                userDiv.classList.add('user');
                userDiv.innerHTML = `
                    <h3>${user.display_name || user.primary_username}</h3>
                    <p class="meta">@${user.primary_username}</p>
                    ${user.is_verified ? '<p class="badge">⭐️ Verified Account</p>' : ''}
                    <a href="/submit_message/${user.primary_username}">Send a Message</a>
                `;
                userList.appendChild(userDiv);
                console.log('Added user:', user.primary_username); // Debug
            });
        } else {
            console.log('No users found to display.'); // Debug
            userList.innerHTML = '<p>No users found.</p>'; // Show this message if no users are found
        }
    }

    function clearSearch() {
        searchInput.value = ''; // Clear the input
        clearIcon.style.visibility = 'hidden'; // Hide the clear icon
        searchUsers(); // Reset the user view
    }

    updatePlaceholder(); // Set initial placeholder text when page loads
});

function reportUser(username, displayName, bio) {
    const messageContent = `Reported user: ${displayName}\n\nBio: ${bio || 'No bio.'}\n\nReason:`;
    const encodedMessage = encodeURIComponent(messageContent);
    const submissionUrl = `/submit_message/admin?prefill=${encodedMessage}`;
    window.location.href = submissionUrl;
}
