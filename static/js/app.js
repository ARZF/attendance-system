document.addEventListener("submit", (event) => {
  if (!event.target.hasAttribute("hx-post")) {
    event.target.querySelectorAll("button[type='submit']").forEach((button) => {
      button.disabled = true;
    });
  }
});

document.addEventListener("htmx:beforeRequest", () => {
  document.getElementById("request-status").textContent = "Saving...";
  document.getElementById("request-error").hidden = true;
});

document.addEventListener("htmx:afterRequest", (event) => {
  document.getElementById("request-status").textContent = "";
  document.getElementById("request-error").hidden = event.detail.successful;
});

window.addEventListener("pageshow", () => {
  document.querySelectorAll("button[type='submit']").forEach((button) => {
    button.disabled = false;
  });
});
