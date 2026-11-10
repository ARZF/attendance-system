(() => {
  const app = document.getElementById("user-management-app");
  if (!app) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const alertBox = document.getElementById("user-management-alert");
  const statusLine = document.getElementById("user-management-status");
  const endpointFor = (name, id) => app.dataset[name].replace("/0/", `/${id}/`);

  function showError(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
  }

  function errorMessage(data, fallback) {
    if (!data || !data.errors) return fallback;
    if (Array.isArray(data.errors)) return data.errors.join(" ");
    return Object.values(data.errors).flat().join(" ");
  }

  async function submit(url, body) {
    alertBox.hidden = true;
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-CSRFToken": csrfToken },
      body,
    });
    if (response.redirected && response.url.includes("/login/")) {
      window.location.assign(response.url);
      throw new Error("Your session expired. Sign in again.");
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorMessage(data, `Request failed (${response.status}).`));
    return data;
  }

  async function handle(form, button, url, body, successMessage) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Saving";
    try {
      await submit(url, body);
      sessionStorage.setItem("user-management-status", successMessage);
      window.location.reload();
    } catch (error) {
      showError(error.message);
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  const savedStatus = sessionStorage.getItem("user-management-status");
  if (savedStatus) {
    statusLine.textContent = savedStatus;
    sessionStorage.removeItem("user-management-status");
  }

  document.getElementById("create-user-form").addEventListener("submit", (event) => {
    event.preventDefault();
    handle(
      event.currentTarget,
      event.submitter,
      app.dataset.createUrl,
      new URLSearchParams(new FormData(event.currentTarget)),
      "User created.",
    );
  });

  document.querySelectorAll("[data-user-update]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      handle(
        form,
        event.submitter,
        endpointFor("updateUrl", form.dataset.userUpdate),
        new URLSearchParams(new FormData(form)),
        "User profile saved.",
      );
    });
  });

  document.querySelectorAll("[data-user-status]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const isActive = form.dataset.active === "true";
      if (!window.confirm(`${isActive ? "Deactivate" : "Activate"} this account?`)) return;
      const body = new URLSearchParams();
      if (!isActive) body.set("is_active", "on");
      handle(
        form,
        event.submitter,
        endpointFor("statusUrl", form.dataset.userStatus),
        body,
        `Account ${isActive ? "deactivated" : "activated"}.`,
      );
    });
  });
})();
