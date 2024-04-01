document.addEventListener('DOMContentLoaded', function() {
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
