document.addEventListener("DOMContentLoaded", async function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const subscribeForm = document.querySelector("#subscribe-form");
  const processingPayment = document.querySelector("#processing-payment");

  // Show #subscribe-form and hide #processing-payment
  subscribeForm.style.display = "block";
  processingPayment.style.display = "none";

  const stripeClientSecret = document.querySelector(
    "input[name='stripe_client_secret']",
  ).value;
  const stripePublishableKey = document.querySelector(
    "input[name='stripe_publishable_key']",
  ).value;

  stripe = Stripe(stripePublishableKey);
  const elements = stripe.elements();

  // Check if the user prefers dark mode
  const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;

  // Apply dark mode styles
  const style = {
    base: {
      color: isDarkMode ? '#ffffff' : '#000000',
      fontSize: '16px',
      '::placeholder': {
        color: isDarkMode ? '#ffffff' : '#a0a0a0',
      },
    },
  };

  const cardElement = elements.create("card", { style: style });
  cardElement.mount("#card-element");

  const form = document.querySelector("#subscribe-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("name");

    // Create payment method and confirm payment intent
    const result = await stripe.confirmCardPayment(stripeClientSecret, {
      payment_method: {
        card: cardElement,
        billing_details: {
          name: nameInput.value,
        },
      },
    });

    if (result.error) {
      alert(`Payment failed: ${result.error.message}`);
      return;
    } else {
      // Processing payment
      subscribeForm.style.display = "none";
      processingPayment.style.display = "block";

      // Check for payment status every 2 seconds
      setInterval(() => {
        fetch(`${pathPrefix}/status.json`)
          .then((response) => response.json())
          .then((data) => {
            if (data.tier_id === 2) {
              // Payment successful, redirect to premium home
              window.location.href = pathPrefix;
            } else {
              console.log("Payment status not yet confirmed.", data);
            }
          })
          .catch((error) =>
            console.error("Failed to load payment status:", error),
          );
      }, 2000);
    }
  });
});