document.addEventListener('DOMContentLoaded', function() {
    var stripe = Stripe('pk_live_51OhDeALcBPqjxU07qsU5iItym6nEJFMYMre1etoqGZ99CqUZYJAiSYSMnexReokI8T0mcBuYZK59Lg7V8cVsrwkR00EtUil3mg');

    // Handle the "Upgrade Now" button click
    const checkoutButton = document.getElementById('checkout-button');
    if (checkoutButton) {
        checkoutButton.addEventListener('click', function(event) {
            event.preventDefault();
            fetch('/create-checkout-session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(function(response) {
                return response.json();
            })
            .then(function(session) {
                if(session.id) {
                    return stripe.redirectToCheckout({ sessionId: session.id });
                } else {
                    throw new Error('Session ID not found');
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
            });
        });
    }

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
});
