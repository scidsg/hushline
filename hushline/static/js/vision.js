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

async function processFile(file, resultsContainer) {
    const reader = new FileReader();
    reader.onload = async function (e) {
        const imgElement = document.createElement('img');
        imgElement.src = e.target.result;
        imgElement.style.display = 'none';

        const resultDiv = document.createElement('div');
        resultDiv.innerHTML = `<strong>Processing ${file.name}...</strong>`;
        resultsContainer.appendChild(resultDiv);

        // Append the image to the DOM before setting onload to ensure it loads correctly
        document.body.appendChild(imgElement);

        imgElement.onload = () => {
            Tesseract.recognize(
                imgElement,
                'eng',
                {
                    logger: info => {
                        resultDiv.innerHTML = `<p class="file-name">${file.name}</p><p class="meta">Progress: ${Math.round(info.progress * 100)}%</p>`;
                    }
                }
            ).then(({ data: { text } }) => {
                resultDiv.innerHTML = `<p class="file-name">${file.name}</p><p><span class="bold">Detected Text:</span><br>${text}</p>`;
                document.body.removeChild(imgElement); // Remove image after processing
            }).catch(err => {
                resultDiv.innerHTML = `<p class="file-name">${file.name}</p><p><span class="bold">Error:</span><br>${err.message}</p>`;
                document.body.removeChild(imgElement); // Remove image even if there is an error
            });
        };
    };

    reader.readAsDataURL(file);
}