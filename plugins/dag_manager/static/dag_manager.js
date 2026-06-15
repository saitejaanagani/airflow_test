(() => {
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

  const modal = document.querySelector("[data-create-modal]");
  const openModal = document.querySelector("[data-open-create-modal]");
  const closeModal = document.querySelector("[data-close-create-modal]");
  if (modal && openModal && closeModal) {
    openModal.addEventListener("click", () => {
      modal.hidden = false;
      closeModal.focus();
    });
    closeModal.addEventListener("click", () => {
      modal.hidden = true;
      openModal.focus();
    });
    modal.addEventListener("click", (event) => {
      if (event.target === modal) modal.hidden = true;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
        modal.hidden = true;
        openModal.focus();
      }
    });
  }

  const form = document.querySelector("[data-dag-form]");
  const submit = document.querySelector("[data-submit-dag]");
  if (form && submit) {
    const requiredFields = Array.from(form.querySelectorAll("[data-required='true']"));
    const isFilled = (field) => {
      if (field.type === "checkbox") return field.checked;
      return String(field.value || "").trim().length > 0 && field.checkValidity();
    };
    const updateSubmitState = () => {
      submit.disabled = requiredFields.some((field) => !isFilled(field));
    };
    requiredFields.forEach((field) => {
      field.addEventListener("input", updateSubmitState);
      field.addEventListener("change", updateSubmitState);
    });
    updateSubmitState();
  }
})();
