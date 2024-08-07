document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('fileInput').addEventListener('change', handleFilesSelect, false);
});

async function handleFilesSelect(evt) {
    const files = evt.target.files;
    if (!files.length) return;

    const resultsContainer = document.getElementById('results');
    resultsContainer.innerHTML = ''; // Clear previous results

    for (const file of files) {
        await processFile(file, resultsContainer);
    }
}

// More at https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html#output-encoding-for-html-contexts
function escapeHTML(str) {
    return str.replace(/[&<>"']/g, function (m) {
        return {
            '&': '&amp;',  // Escape ampersand
            '<': '&lt;',   // Escape less than
            '>': '&gt;',   // Escape greater than
            '"': '&quot;', // Escape double quote
            "'": '&#x27;'  // Escape single quote (also could use &apos;)
        }[m];
    });
}

async function processFile(file, resultsContainer) {
    const reader = new FileReader();
    reader.onload = async function (e) {
        const imgElement = document.createElement('img');
        imgElement.src = e.target.result;
        imgElement.style.display = 'none';

        const resultDiv = document.createElement('div');
        resultDiv.textContent = `Processing ${file.name}...`; // Safe text content
        resultsContainer.appendChild(resultDiv);

        // Append the image to the DOM before setting onload to ensure it loads correctly
        document.body.appendChild(imgElement);

        imgElement.onload = () => {
            Tesseract.recognize(
                imgElement,
                'eng',
                {
                    logger: info => {
                        resultDiv.innerHTML = `<p class="file-name">${escapeHTML(file.name)}</p><p class="meta">Progress: ${Math.round(info.progress * 100)}%</p>`;
                    }
                }
            ).then(({ data: { text } }) => {
                resultDiv.innerHTML = `<p class="file-name">${escapeHTML(file.name)}</p><p><span class="bold">Detected Text:</span><br>${escapeHTML(text)}</p>`;
                document.body.removeChild(imgElement); // Remove image after processing
            }).catch(err => {
                resultDiv.innerHTML = `<p class="file-name">${escapeHTML(file.name)}</p><p><span class="bold">Error:</span><br>${escapeHTML(err.message)}</p>`;
                document.body.removeChild(imgElement); // Remove image even if there is an error
            });
        };
    };

    reader.readAsDataURL(file);
}