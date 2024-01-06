document.addEventListener('DOMContentLoaded', function() {
        const mobileNavButton = document.querySelector('.mobileNav');
        const navMenu = document.querySelector('header nav ul');

        mobileNavButton.addEventListener('click', function() {
            navMenu.classList.toggle('show');
        });
    });