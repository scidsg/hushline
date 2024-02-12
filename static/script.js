document.addEventListener('DOMContentLoaded', function() {
    // Initialize Stripe with your Stripe publishable key
    // var stripe = Stripe('pk_live_51OhDeALcBPqjxU07qsU5iItym6nEJFMYMre1etoqGZ99CqUZYJAiSYSMnexReokI8T0mcBuYZK59Lg7V8cVsrwkR00EtUil3mg');
    var stripe = Stripe('pk_test_51OhDeALcBPqjxU07I70UA6JYGDPUmkxEwZW0lvGyNXGlJ4QPfWIBFZJau7XOb3QDzDWrVutBVkz9SNrSjq2vRawm00TwfyFuma');
    
    // Handle mobile navigation toggle
    const mobileNavButton = document.querySelector('.mobileNav');
    const navMenu = document.querySelector('header nav ul');
    
    mobileNavButton.addEventListener('click', function() {
        navMenu.classList.toggle('show');
    });

    // Handle subscription cancellation confirmation
    const cancelSubscriptionForm = document.getElementById('cancelSubscriptionForm');
    if (cancelSubscriptionForm) {
        cancelSubscriptionForm.addEventListener('submit', function(event) {
            const confirmed = confirm('Are you sure you want to cancel your subscription?');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    }

    // Handle account deletion confirmation
    const deleteButton = document.getElementById('deleteAccountButton');
    if (deleteButton) {
        deleteButton.addEventListener('click', function(event) {
            const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    }


    // Handle message deletion confirmation
    const deleteMessageButton = document.getElementById('deleteMessageButton');
    if (deleteMessageButton) {
        deleteMessageButton.addEventListener('click', function(event) {
            const confirmed = confirm('Are you sure you want to delete this message? This cannot be undone.');
            if (!confirmed) {
                event.preventDefault();
            }
        });
    }

    // Handle the "Buy Premium Feature" button click
    const checkoutButton = document.getElementById('checkout-button'); // Ensure your button has this ID
    if (checkoutButton) {
        checkoutButton.addEventListener('click', function(event) {
            event.preventDefault();
            fetch('/create-checkout-session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => {
                if (response.ok) return response.json();
                throw new Error('Network response was not ok.');
            })
            .then(data => {
                // Use Stripe's redirectToCheckout with the session ID
                stripe.redirectToCheckout({ sessionId: data.id });
            })
            .catch(error => console.error('Error:', error));
        });
    }

    // Mailvelope decryption logic
    const encryptedMessages = document.querySelectorAll('.message.encrypted');
    encryptedMessages.forEach(messageElement => {
        const encryptedContent = messageElement.dataset.encryptedContent;
        const decryptionContainer = messageElement.querySelector('.mailvelope-decryption-container');

        if (window.mailvelope) {
            mailvelope.createDisplayContainer({
                id: decryptionContainer.getAttribute('id'),
                encryptedMsg: encryptedContent
            }).then(displayContainer => {
                messageElement.querySelector('.decrypted-content').style.display = 'none'; // Hide original content
                decryptionContainer.appendChild(displayContainer.element);
            }).catch(error => {
                console.error('Decryption error:', error);
                // Handle error or inform user
            });
        } else {
            console.log('Mailvelope not detected');
            // Inform user or provide instructions for installing Mailvelope
        }
    });

    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    function removeActiveClasses() {
        tabs.forEach(tab => {
            tab.classList.remove('active');
        });
        tabContents.forEach(content => {
            content.style.display = 'none'; // Hide all tab content initially
        });
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            removeActiveClasses();
            this.classList.add('active');
            const activeTabContent = document.getElementById(this.getAttribute('data-tab'));
            if (activeTabContent) {
                activeTabContent.style.display = 'block'; // Show the active tab content
            }
        });
    });

    if (tabs.length > 0) {
        tabs[0].click(); // Open the first tab automatically
    }
});
