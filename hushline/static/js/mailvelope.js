document.addEventListener('DOMContentLoaded', function() {
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
});
