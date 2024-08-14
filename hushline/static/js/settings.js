document.addEventListener('DOMContentLoaded', function () {
    const tabs = document.querySelectorAll('.tab');
    const tabPanels = document.querySelectorAll('.tab-content');
    const bioCountEl = document.querySelector('.bio-count');
    // Deletion account confirmation logic
    document.getElementById('deleteAccountButton')?.addEventListener('click', function (event) {
        const confirmed = confirm('Are you sure you want to delete your account? This cannot be undone.');
        if (!confirmed) {
            event.preventDefault();
        }
    });

    document.querySelector("input[name='show_in_directory']").addEventListener('change', function (e) {
        // time out to let animation finish
        setTimeout(() => {
            document.querySelector("button[name='update_directory_visibility']").click();
        }, 200)
    });

    document.getElementById('bio').addEventListener('keyup', function (e) {
        bioCountEl.textContent = e.target.value.length;
    });

    tabs.forEach(tab => {
        tab.addEventListener('click', function (e) {
            window.activateTab(e, tabs, tabPanels);
        });
        tab.addEventListener('keydown', function (e) {
            window.handleKeydown(e)
        });
    });

    // PGP subtabs
    const pgpProtonTab = document.querySelector('.subtab-pgp-proton');
    const pgpProtonTabContent = document.getElementById('pgp-proton');
    const pgpPublicKeyTab = document.querySelector('.subtab-pgp-public-key');
    const pgpPublicKeyTabContent = document.getElementById('pgp-public-key');

    pgpProtonTab.addEventListener('click', function (e) {
        pgpProtonTab.classList.add('active');
        pgpProtonTabContent.classList.add('active');
        pgpProtonTabContent.hidden = false;

        pgpPublicKeyTab.classList.remove('active');
        pgpPublicKeyTabContent.classList.remove('active');
        pgpPublicKeyTabContent.hidden = true;
    });
    pgpPublicKeyTab.addEventListener('click', function (e) {
        pgpPublicKeyTab.classList.add('active');
        pgpPublicKeyTabContent.classList.add('active');
        pgpPublicKeyTabContent.hidden = false;

        pgpProtonTab.classList.remove('active');
        pgpProtonTabContent.classList.remove('active');
        pgpProtonTabContent.hidden = true;
    });

    // If there's a PGP key set, show the public key tab
    if (document.getElementById('pgp_key').value != "") {
        pgpPublicKeyTab.click();
    }
});
