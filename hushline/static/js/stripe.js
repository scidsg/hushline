document.addEventListener('DOMContentLoaded', function() {
    var stripe = Stripe('pk_test_51OhDeALcBPqjxU07I70UA6JYGDPUmkxEwZW0lvGyNXGlJ4QPfWIBFZJau7XOb3QDzDWrVutBVkz9SNrSjq2vRawm00TwfyFuma');

    const checkoutButton = document.getElementById('checkout-button');
    checkoutButton.addEventListener('click', function(event) {
        event.preventDefault();
        fetch('/create-checkout-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => stripe.redirectToCheckout({ sessionId: data.id }))
        .catch(error => console.error('Error:', error));
    });

    // Handle subscription cancellation confirmation
    const cancelSubscriptionForm = document.getElementById('cancelSubscriptionForm');
    if (cancelSubscriptionForm) {
        cancelSubscriptionForm.addEventListener('submit', function(event) {
            const confirmed = confirm('Are you sure you want to cancel your subscription?');
            if (!confirmed) {
                event.preventDefault(); // Stop the form submission if the user does not confirm
            }
        });
    }
});
