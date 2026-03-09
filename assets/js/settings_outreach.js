document.addEventListener("DOMContentLoaded", function () {
  const outreachTabs = document.getElementById("outreach-tabs");
  if (!outreachTabs) {
    return;
  }

  const tabs = outreachTabs.querySelectorAll(".tab[data-tab]");
  const panels = document.querySelectorAll('.tab-content[id^="outreach-"]');

  function sourceFromPanelId(panelId) {
    return panelId.replace("outreach-", "").replaceAll("-", "_");
  }

  function activateTab(selectedTab) {
    const targetPanel = document.getElementById(selectedTab.getAttribute("aria-controls"));
    if (!targetPanel) {
      return;
    }

    tabs.forEach((tab) => {
      tab.classList.remove("active");
      tab.setAttribute("aria-selected", "false");
    });
    panels.forEach((panel) => {
      panel.classList.remove("active");
      panel.hidden = true;
      panel.style.display = "none";
    });

    selectedTab.classList.add("active");
    selectedTab.setAttribute("aria-selected", "true");
    targetPanel.classList.add("active");
    targetPanel.hidden = false;
    targetPanel.style.display = "block";

    const url = new URL(window.location.href);
    url.searchParams.set("source", sourceFromPanelId(targetPanel.id));
    window.history.replaceState({}, "", url);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", function () {
      activateTab(tab);
    });
    tab.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      event.preventDefault();
      const tabArray = Array.from(tabs);
      const currentIndex = tabArray.indexOf(tab);
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextIndex = (currentIndex + direction + tabArray.length) % tabArray.length;
      const nextTab = tabArray[nextIndex];
      if (nextTab) {
        activateTab(nextTab);
        nextTab.focus();
      }
    });
  });

  const defaultTab = outreachTabs.querySelector(".tab.active") || tabs[0];
  if (defaultTab) {
    activateTab(defaultTab);
  }
});
