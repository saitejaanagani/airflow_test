(() => {
  const templateToggle = document.querySelector("[data-template-menu-toggle]");
  const templateMenu = document.querySelector("[data-template-menu]");
  if (templateToggle && templateMenu) {
    templateToggle.addEventListener("click", () => {
      templateMenu.classList.toggle("is-hidden");
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

  const form = document.querySelector("[data-dag-form]");
  const submitButton = document.querySelector("[data-submit-button]");
  if (form && submitButton) {
    const syncSubmitState = () => {
      submitButton.disabled = !form.checkValidity();
    };

    form.addEventListener("input", syncSubmitState);
    form.addEventListener("change", syncSubmitState);
    syncSubmitState();
  }
})();
