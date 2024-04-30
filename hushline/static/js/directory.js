document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = document.querySelector('#' + tab.getAttribute('data-tab'));

            // Remove active class from all tabs and contents
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            // Add active class to clicked tab and corresponding content
            tab.classList.add('active');
            target.classList.add('active');
        });
    });
});

function reportUser(username, displayName, bio) {
    // Construct the message content with explicit line breaks
    const messageContent = `Reported user: ${displayName}\n\nBio: ${bio || 'No bio.'}\n\nReason:`;

    // Encode the message content to ensure line breaks and other special characters are correctly handled
    const encodedMessage = encodeURIComponent(messageContent);

    // Redirect to the message submission form for the admin with the pre-filled content
    const submissionUrl = `/submit_message/admin?prefill=${encodedMessage}`;
    window.location.href = submissionUrl;
}
