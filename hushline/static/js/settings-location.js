document.addEventListener("DOMContentLoaded", function () {
  const countryInput = document.getElementById("country");
  const subdivisionInput = document.getElementById("subdivision");
  const cityInput = document.getElementById("city");

  if (!countryInput || !subdivisionInput || !cityInput) {
    return;
  }

  const statesUrl = countryInput.dataset.statesUrl;
  const citiesUrl = subdivisionInput.dataset.citiesUrl;

  function setDisabledState(input, disabled) {
    input.disabled = disabled;
    input.setAttribute("aria-disabled", disabled ? "true" : "false");
  }

  function renderOptions(select, placeholder, options, selectedValue) {
    const nextOptions = [{ value: "", label: placeholder }, ...options];
    select.innerHTML = "";

    nextOptions.forEach(function (option) {
      const optionElement = document.createElement("option");
      optionElement.value = option.value;
      optionElement.textContent = option.label;
      select.appendChild(optionElement);
    });

    const validValues = new Set(
      nextOptions.map(function (option) {
        return option.value;
      }),
    );
    select.value = validValues.has(selectedValue) ? selectedValue : "";
  }

  async function loadStates(selectedValue) {
    const country = countryInput.value.trim();
    if (!country || !statesUrl) {
      renderOptions(subdivisionInput, "Select", [], "");
      renderOptions(cityInput, "Select", [], "");
      setDisabledState(subdivisionInput, true);
      setDisabledState(cityInput, true);
      return;
    }

    const response = await fetch(
      `${statesUrl}?country=${encodeURIComponent(country)}`,
    );
    const payload = await response.json();
    const states = Array.isArray(payload.states) ? payload.states : [];
    renderOptions(subdivisionInput, "Select", states, selectedValue);
    setDisabledState(subdivisionInput, false);

    if (!subdivisionInput.value) {
      renderOptions(cityInput, "Select", [], "");
      setDisabledState(cityInput, true);
    }
  }

  async function loadCities(selectedValue) {
    const country = countryInput.value.trim();
    const subdivision = subdivisionInput.value.trim();
    if (!country || !subdivision || !citiesUrl) {
      renderOptions(cityInput, "Select", [], "");
      setDisabledState(cityInput, true);
      return;
    }

    const params = new URLSearchParams({
      country,
      subdivision,
    });
    const response = await fetch(`${citiesUrl}?${params.toString()}`);
    const payload = await response.json();
    const cities = Array.isArray(payload.cities) ? payload.cities : [];
    renderOptions(cityInput, "Select", cities, selectedValue);
    setDisabledState(cityInput, false);
  }

  countryInput.addEventListener("change", async function () {
    await loadStates("");
  });

  subdivisionInput.addEventListener("change", async function () {
    await loadCities("");
  });

  (async function syncLocationInputs() {
    setDisabledState(subdivisionInput, !countryInput.value.trim());
    setDisabledState(cityInput, !subdivisionInput.value.trim());
    await loadStates(subdivisionInput.value);
    await loadCities(cityInput.value);
  })();
});
