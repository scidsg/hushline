document.addEventListener('DOMContentLoaded', function() {
    // Isolate dropdown setup in its own function for better error handling
    function setupDropdown() {
        const dropdownToggle = document.querySelector('.dropdown .dropbtn');
        if (!dropdownToggle) return; // Exit if no dropdown toggle found

        const dropdownContent = document.querySelector('.dropdown-content');
        const dropdownIcon = document.querySelector('.dropdown-icon');

        // Ensure all elements needed for the dropdown are present
        if (dropdownContent && dropdownIcon) {
            dropdownToggle.addEventListener('click', function(event) {
                event.preventDefault();
                dropdownContent.classList.toggle('show');
                dropdownContent.style.animation = dropdownContent.classList.contains('show') ? 'fadeInSlideDown 0.3s ease forwards' : 'fadeOutSlideUp 0.3s ease forwards';
                dropdownIcon.classList.toggle('rotate-icon');
            });

            window.addEventListener('click', function(event) {
                if (!dropdownToggle.contains(event.target) && dropdownContent.classList.contains('show')) {
                    dropdownContent.classList.remove('show');
                    dropdownIcon.classList.remove('rotate-icon');
                }
            });
        }
    }

    // Execute dropdown setup
    setupDropdown();

    // Handle message deletion confirmation
    document.getElementById('deleteMessageButton')?.addEventListener('click', function(event) {
        const confirmed = confirm('Are you sure you want to delete this message? This cannot be undone.');
        if (!confirmed) {
            event.preventDefault();
        }
    });

    // Mailvelope decryption logic
    const encryptedMessages = document.querySelectorAll('.message.encrypted');
    encryptedMessages.forEach(messageElement => {
        const encryptedContent = messageElement.dataset.encryptedContent;
        const decryptionContainer = messageElement.querySelector('.mailvelope-decryption-container');

        if (window.mailvelope) {
            mailvelope.createDisplayContainer({
                id: decryptionContainer.getAttribute('id'),
                encryptedMsg: encryptedContent,
            }).then(displayContainer => {
                messageElement.querySelector('.decrypted-content').style.display = 'none';
                decryptionContainer.appendChild(displayContainer.element);
            }).catch(error => {
                console.error('Decryption error:', error);
            });
        } else {
            console.log('Mailvelope not detected');
        }
    });

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

    // Client-side encryption
    const form = document.getElementById('messageForm');
    const messageField = document.querySelector('textarea[name="content"]');
    const encryptedFlag = document.getElementById('clientSideEncrypted');
    const publicKeyArmored = document.getElementById('publicKey') ? document.getElementById('publicKey').value : '';

    async function encryptMessage(publicKeyArmored, message) {
        if (!publicKeyArmored) {
            console.log('Public key not provided for encryption. Encryption cannot proceed.');
            return false;
        }

        try {
            const publicKey = await openpgp.readKey({ armoredKey: publicKeyArmored });
            const messageText = await openpgp.createMessage({ text: message });
            const encryptedMessage = await openpgp.encrypt({
                message: messageText,
                encryptionKeys: publicKey,
            });
            console.log('Message encrypted client-side successfully.');
            return encryptedMessage;
        } catch (error) {
            console.error('Error encrypting message:', error);
            return false;
        }
    }

    if (form) {
        form.addEventListener('submit', async function(event) {
            event.preventDefault();

            const messageWithNote = messageField.value;
            const encryptedMessage = await encryptMessage(publicKeyArmored, messageWithNote);

            if (encryptedMessage) {
                messageField.value = encryptedMessage;
                encryptedFlag.value = 'true';
                form.submit(); // Programmatically submit the form
            } else {
                console.log('Client-side encryption failed, submitting plaintext.');
                encryptedFlag.value = 'false';
                form.submit(); // Submit the plaintext message for potential server-side encryption
            }
        });
    }
});
