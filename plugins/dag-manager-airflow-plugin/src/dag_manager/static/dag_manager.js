(() => {
  const switcher = document.querySelector("[data-template-switcher]");
  if (switcher) {
    switcher.addEventListener("change", () => {
      const target = switcher.dataset.newUrl;
      window.location.href = `${target}?template_key=${encodeURIComponent(switcher.value)}`;
    });
  }

  const tabs = document.querySelectorAll("[data-section-target]");
  const sections = document.querySelectorAll("[data-section]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.classList.remove("is-active"));
      sections.forEach((section) => section.classList.add("is-hidden"));
      tab.classList.add("is-active");
      const selected = document.querySelector(`[data-section="${tab.dataset.sectionTarget}"]`);
      if (selected) selected.classList.remove("is-hidden");
    });
  });
})();
