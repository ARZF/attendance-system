(() => {
  const app = document.getElementById("attendance-app");
  if (!app) return;

  const role = app.dataset.role;
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const alertBox = document.getElementById("attendance-alert");
  const statusLine = document.getElementById("attendance-status");
  const reportForm = document.getElementById("report-filter");
  const dateTime = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Tehran",
  });
  const localParts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Tehran",
  });
  let reportPage = 1;
  let selectedEmployeeId = "";
  let dialogSession = null;

  const endpoint = (name) => app.dataset[name];
  const endpointFor = (name, id) => endpoint(name).replace("/0/", `/${id}/`);

  function showError(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
  }

  function clearError() {
    alertBox.hidden = true;
    alertBox.textContent = "";
  }

  function showStatus(message) {
    statusLine.textContent = message;
  }

  function errorMessage(data, fallback) {
    if (!data || !data.errors) return fallback;
    if (Array.isArray(data.errors)) return data.errors.join(" ");
    return Object.values(data.errors).flat().join(" ");
  }

  async function requestJson(url, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.method && options.method !== "GET") headers["X-CSRFToken"] = csrfToken;
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers,
    });
    if (response.redirected && response.url.includes("/login/")) {
      window.location.assign(response.url);
      throw new Error("Your session expired. Sign in again.");
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorMessage(data, `Request failed (${response.status}).`));
    return data;
  }

  async function withPending(button, pendingText, task) {
    const originalText = button.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = pendingText;
    try {
      return await task();
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = originalText;
    }
  }

  function formatDate(value) {
    if (!value) return "Not recorded";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "Invalid date" : dateTime.format(parsed);
  }

  function inputDateTime(value = new Date()) {
    const parts = {};
    for (const part of localParts.formatToParts(new Date(value))) {
      if (part.type !== "literal") parts[part.type] = part.value;
    }
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  }

  function formatDuration(seconds) {
    const wholeMinutes = Math.max(0, Math.floor(Number(seconds) / 60));
    const hours = Math.floor(wholeMinutes / 60);
    const minutes = wholeMinutes % 60;
    if (!hours) return `${minutes}m`;
    return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  }

  function sessionDuration(session) {
    if (!session.check_out_at) return "Active";
    return formatDuration((new Date(session.check_out_at) - new Date(session.check_in_at)) / 1000);
  }

  function displayType(value) {
    return value === "CHECK_IN" ? "Check in" : "Check out";
  }

  function displayStatus(value) {
    return value.charAt(0) + value.slice(1).toLowerCase();
  }

  function cell(row, label, value) {
    const item = document.createElement("td");
    item.dataset.label = label;
    if (value instanceof Node) item.append(value);
    else item.textContent = value;
    row.append(item);
    return item;
  }

  function emptyRow(body, columnCount, message) {
    body.replaceChildren();
    const row = document.createElement("tr");
    const item = document.createElement("td");
    item.colSpan = columnCount;
    item.textContent = message;
    row.append(item);
    body.append(row);
  }

  function formQuery(form, additions = {}) {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form).entries()) {
      if (value !== "") params.set(key, value);
    }
    for (const [key, value] of Object.entries(additions)) params.set(key, value);
    return params;
  }

  async function loadSelfDashboard() {
    const data = await requestJson(endpoint("selfDashboardUrl"));
    const activeLabel = document.getElementById("active-session");
    const pendingTypes = new Set(data.pending_requests.map((item) => item.request_type));
    const active = data.active_session;
    activeLabel.textContent = active
      ? `Checked in since ${formatDate(active.check_in_at)}.`
      : "No active attendance session.";

    const checkIn = document.getElementById("check-in-button");
    const checkOut = document.getElementById("check-out-button");
    checkIn.disabled = Boolean(active) || pendingTypes.has("CHECK_IN");
    checkOut.disabled = !active || pendingTypes.has("CHECK_OUT");
  }

  function renderOwnRequests(requests) {
    const body = document.getElementById("own-requests-body");
    if (!requests.length) {
      emptyRow(body, 5, "No attendance requests yet.");
      return;
    }
    body.replaceChildren();
    for (const request of requests) {
      const row = document.createElement("tr");
      cell(row, "Type", displayType(request.request_type));
      cell(row, "Attendance time", formatDate(request.attendance_at));
      cell(row, "Status", displayStatus(request.status));
      cell(row, "Reviewed", request.reviewed_at ? formatDate(request.reviewed_at) : "Not reviewed");
      const actions = document.createElement("div");
      actions.className = "table-actions";
      if (request.status === "PENDING") {
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "secondary";
        cancel.textContent = "Cancel";
        cancel.addEventListener("click", async () => {
          if (!window.confirm("Cancel this attendance request?")) return;
          clearError();
          try {
            await withPending(cancel, "Cancelling", () => requestJson(
              endpointFor("cancelRequestUrl", request.id),
              { method: "POST", body: new URLSearchParams() },
            ));
            showStatus("Attendance request cancelled.");
            await Promise.all([loadSelfDashboard(), loadOwnRequests(), loadRoleDashboard()]);
          } catch (error) {
            showError(error.message);
          }
        });
        actions.append(cancel);
      } else {
        actions.textContent = "None";
      }
      cell(row, "Action", actions);
      body.append(row);
    }
  }

  async function loadOwnRequests() {
    const body = document.getElementById("own-requests-body");
    try {
      const data = await requestJson(`${endpoint("ownRequestsUrl")}?page_size=100`);
      renderOwnRequests(data.requests);
    } catch (error) {
      emptyRow(body, 5, "Could not load request history.");
      showError(error.message);
    }
  }

  function renderReport(data) {
    const body = document.getElementById("report-body");
    const columnCount = role === "EMPLOYEE" ? 3 : 4;
    document.getElementById("report-total").textContent = `Total: ${formatDuration(data.total_working_seconds)}`;
    if (!data.sessions.length) {
      emptyRow(body, columnCount, "No attendance sessions in this range.");
    } else {
      body.replaceChildren();
      for (const session of data.sessions) {
        const row = document.createElement("tr");
        if (role !== "EMPLOYEE") cell(row, "Employee", session.employee_username);
        cell(row, "Check-in", formatDate(session.check_in_at));
        cell(row, "Check-out", session.check_out_at ? formatDate(session.check_out_at) : "Active session");
        cell(row, "Duration", sessionDuration(session));
        body.append(row);
      }
    }
    const pagination = data.pagination;
    reportPage = pagination.page;
    document.getElementById("report-page").textContent = `Page ${pagination.page} of ${pagination.pages}`;
    document.getElementById("report-previous").disabled = pagination.page <= 1;
    document.getElementById("report-next").disabled = pagination.page >= pagination.pages;
  }

  async function loadReport(page = 1) {
    const body = document.getElementById("report-body");
    emptyRow(body, role === "EMPLOYEE" ? 3 : 4, "Loading attendance records.");
    try {
      const query = formQuery(reportForm, { page, page_size: 25 });
      const data = await requestJson(`${endpoint("reportUrl")}?${query}`);
      renderReport(data);
    } catch (error) {
      emptyRow(body, role === "EMPLOYEE" ? 3 : 4, "Could not load attendance records.");
      showError(error.message);
    }
  }

  function renderPendingReviews(requests) {
    const body = document.getElementById("review-requests-body");
    if (!body) return;
    if (!requests.length) {
      emptyRow(body, 5, "No requests are waiting for review.");
      return;
    }
    body.replaceChildren();
    for (const request of requests) {
      const row = document.createElement("tr");
      cell(row, "Employee", request.employee_username);
      cell(row, "Type", displayType(request.request_type));
      cell(row, "Attendance time", formatDate(request.attendance_at));
      cell(row, "Requested", formatDate(request.requested_at));
      const actions = document.createElement("div");
      actions.className = "table-actions";
      const approve = document.createElement("button");
      approve.type = "button";
      approve.textContent = "Approve";
      approve.addEventListener("click", async () => {
        if (!window.confirm(`Approve ${request.employee_username}'s ${displayType(request.request_type).toLowerCase()} request?`)) return;
        clearError();
        try {
          await withPending(approve, "Approving", () => requestJson(
            endpointFor("approveRequestUrl", request.id),
            { method: "POST", body: new URLSearchParams() },
          ));
          showStatus("Attendance request approved.");
          await Promise.all([loadRoleDashboard(), loadReport(reportPage)]);
        } catch (error) {
          showError(error.message);
        }
      });
      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "danger secondary";
      reject.textContent = "Reject";
      reject.addEventListener("click", () => openRejectDialog(request));
      actions.append(approve, reject);
      cell(row, "Actions", actions);
      body.append(row);
    }
  }

  function renderOverview(rows) {
    const body = document.getElementById("overview-body");
    if (!body) return;
    if (!rows.length) {
      emptyRow(body, 4, "No employee attendance is available for this range.");
      return;
    }
    body.replaceChildren();
    for (const item of rows) {
      const row = document.createElement("tr");
      cell(row, "Employee", item.employee_username);
      cell(row, "Completed sessions", String(item.session_count));
      cell(row, "Working time", formatDuration(item.total_working_seconds));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = "View sessions";
      button.addEventListener("click", () => {
        const select = document.getElementById("history-employee");
        select.value = String(item.employee_id);
        selectedEmployeeId = String(item.employee_id);
        loadEmployeeSessions(selectedEmployeeId);
        document.getElementById("employee-sessions-heading").scrollIntoView({ block: "start" });
      });
      cell(row, "Action", button);
      body.append(row);
    }
  }

  async function loadRoleDashboard() {
    if (!endpoint("roleDashboardUrl")) return;
    const params = new URLSearchParams({
      start_date: document.getElementById("report-start").value,
      end_date: document.getElementById("report-end").value,
      page_size: "100",
    });
    try {
      const data = await requestJson(`${endpoint("roleDashboardUrl")}?${params}`);
      renderPendingReviews(data.pending_requests);
      if (role === "ADMIN") {
        const counts = data.counts;
        document.getElementById("count-employees").textContent = counts.active_employees;
        document.getElementById("count-guards").textContent = counts.active_guards;
        document.getElementById("count-sessions").textContent = counts.active_sessions;
        document.getElementById("count-requests").textContent = counts.pending_requests;
        renderOverview(data.attendance_overview);
      } else {
        const overview = new Map(data.attendance_overview.map((item) => [item.employee_id, item]));
        renderOverview(data.assigned_employees.map((employee) => overview.get(employee.id) || {
          employee_id: employee.id,
          employee_username: employee.username,
          session_count: 0,
          total_working_seconds: 0,
        }));
      }
    } catch (error) {
      emptyRow(document.getElementById("review-requests-body"), 5, "Could not load pending requests.");
      emptyRow(document.getElementById("overview-body"), 4, "Could not load the attendance overview.");
      showError(error.message);
    }
  }

  function openRejectDialog(request) {
    const dialog = document.getElementById("reject-dialog");
    document.getElementById("reject-request-id").value = request.id;
    document.getElementById("reject-request-summary").textContent = `${request.employee_username}: ${displayType(request.request_type)} at ${formatDate(request.attendance_at)}.`;
    document.getElementById("rejection-reason").value = "";
    dialog.showModal();
    document.getElementById("rejection-reason").focus();
  }

  function renderEmployeeSessions(data) {
    const body = document.getElementById("employee-sessions-body");
    document.getElementById("employee-sessions-caption").textContent = `Sessions for ${data.employee.username}`;
    if (!data.sessions.length) {
      emptyRow(body, 4, "No sessions for this employee in the selected range.");
      return;
    }
    body.replaceChildren();
    for (const session of data.sessions) {
      const row = document.createElement("tr");
      cell(row, "Check-in", formatDate(session.check_in_at));
      cell(row, "Check-out", session.check_out_at ? formatDate(session.check_out_at) : "Active session");
      cell(row, "Duration", sessionDuration(session));
      const actions = document.createElement("div");
      actions.className = "table-actions";
      const adjust = document.createElement("button");
      adjust.type = "button";
      adjust.className = "secondary";
      adjust.textContent = "Correct time";
      adjust.addEventListener("click", () => openSessionDialog(session, "correct"));
      actions.append(adjust);
      if (!session.check_out_at) {
        const close = document.createElement("button");
        close.type = "button";
        close.textContent = "Close session";
        close.addEventListener("click", () => openSessionDialog(session, "close"));
        actions.append(close);
      }
      cell(row, "Actions", actions);
      body.append(row);
    }
  }

  async function loadEmployeeSessions(employeeId) {
    if (!employeeId) return;
    selectedEmployeeId = employeeId;
    const body = document.getElementById("employee-sessions-body");
    emptyRow(body, 4, "Loading employee sessions.");
    const params = new URLSearchParams({
      start_date: document.getElementById("report-start").value,
      end_date: document.getElementById("report-end").value,
      page_size: "100",
    });
    try {
      const data = await requestJson(`${endpointFor("scopedHistoryUrl", employeeId)}?${params}`);
      renderEmployeeSessions(data);
    } catch (error) {
      emptyRow(body, 4, "Could not load employee sessions.");
      showError(error.message);
    }
  }

  function openSessionDialog(session, mode) {
    dialogSession = session;
    const dialog = document.getElementById("session-dialog");
    const correctionForm = document.getElementById("correction-form");
    const closeForm = document.getElementById("close-session-form");
    correctionForm.hidden = mode !== "correct";
    closeForm.hidden = mode !== "close";
    document.getElementById("session-dialog-title").textContent = mode === "correct" ? "Correct session time" : "Close active session";
    document.getElementById("session-dialog-summary").textContent = `Check-in: ${formatDate(session.check_in_at)}. Check-out: ${session.check_out_at ? formatDate(session.check_out_at) : "not recorded"}.`;
    if (mode === "correct") {
      document.getElementById("correction-session-id").value = session.id;
      const field = document.getElementById("corrected-field");
      field.querySelector('option[value="CHECK_OUT_AT"]').disabled = !session.check_out_at;
      field.value = "CHECK_IN_AT";
      document.getElementById("correction-value").value = inputDateTime(session.check_in_at);
      document.getElementById("correction-reason").value = "";
    } else {
      document.getElementById("close-session-id").value = session.id;
      document.getElementById("close-session-time").value = inputDateTime();
      document.getElementById("close-session-reason").value = "";
    }
    dialog.showModal();
    dialog.querySelector("form:not([hidden]) input:not([type='hidden']), form:not([hidden]) select").focus();
  }

  async function refreshAfterSessionChange() {
    document.getElementById("session-dialog").close();
    await Promise.all([
      loadEmployeeSessions(selectedEmployeeId),
      loadReport(reportPage),
      loadRoleDashboard(),
    ]);
  }

  function appendLimitNotice(body, columnCount, pagination) {
    if (pagination.pages <= 1) return;
    const row = document.createElement("tr");
    const item = document.createElement("td");
    item.colSpan = columnCount;
    item.textContent = `Showing the first ${pagination.page_size} of ${pagination.total} records. Narrow the filters to find older records.`;
    row.append(item);
    body.append(row);
  }

  async function loadAdminRequests() {
    const form = document.getElementById("admin-request-filter");
    if (!form) return;
    const body = document.getElementById("admin-requests-body");
    emptyRow(body, 5, "Loading request history.");
    try {
      const query = formQuery(form, { page_size: 100 });
      const data = await requestJson(`${endpoint("adminRequestsUrl")}?${query}`);
      if (!data.requests.length) {
        emptyRow(body, 5, "No requests match these filters.");
        return;
      }
      body.replaceChildren();
      for (const request of data.requests) {
        const row = document.createElement("tr");
        cell(row, "Employee", request.employee_username);
        cell(row, "Type", displayType(request.request_type));
        cell(row, "Attendance time", formatDate(request.attendance_at));
        cell(row, "Status", displayStatus(request.status));
        cell(row, "Reviewed", request.reviewed_at ? formatDate(request.reviewed_at) : "Not reviewed");
        body.append(row);
      }
      appendLimitNotice(body, 5, data.pagination);
    } catch (error) {
      emptyRow(body, 5, "Could not load request history.");
      showError(error.message);
    }
  }

  async function loadAdminAssignments() {
    const form = document.getElementById("admin-assignment-filter");
    const body = document.getElementById("admin-assignments-body");
    emptyRow(body, 4, "Loading assignment history.");
    try {
      const query = formQuery(form, { page_size: 100 });
      const data = await requestJson(`${endpoint("adminAssignmentsUrl")}?${query}`);
      if (!data.assignments.length) {
        emptyRow(body, 4, "No assignments match this filter.");
        return;
      }
      body.replaceChildren();
      for (const assignment of data.assignments) {
        const row = document.createElement("tr");
        cell(row, "Employee", assignment.employee_username);
        cell(row, "Guard", assignment.guard_username);
        cell(row, "Started", formatDate(assignment.started_at));
        cell(row, "Ended", assignment.ended_at ? formatDate(assignment.ended_at) : "Current assignment");
        body.append(row);
      }
      appendLimitNotice(body, 4, data.pagination);
    } catch (error) {
      emptyRow(body, 4, "Could not load assignment history.");
      showError(error.message);
    }
  }

  async function loadAdminAudit() {
    const form = document.getElementById("admin-audit-filter");
    const body = document.getElementById("admin-audit-body");
    emptyRow(body, 5, "Loading audit events.");
    try {
      const query = formQuery(form, { page_size: 100 });
      const data = await requestJson(`${endpoint("adminAuditUrl")}?${query}`);
      if (!data.audit_logs.length) {
        emptyRow(body, 5, "No audit events match these filters.");
        return;
      }
      body.replaceChildren();
      for (const event of data.audit_logs) {
        const row = document.createElement("tr");
        cell(row, "Time", formatDate(event.created_at));
        cell(row, "Action", event.action);
        cell(row, "Actor", event.actor_id ? String(event.actor_id) : "System");
        cell(row, "Target", event.target_employee_id ? `Employee ${event.target_employee_id}` : `${event.target_type || "Record"} ${event.target_id || ""}`.trim());
        cell(row, "Details", Object.keys(event.details).length ? JSON.stringify(event.details) : "None");
        body.append(row);
      }
      appendLimitNotice(body, 5, data.pagination);
    } catch (error) {
      emptyRow(body, 5, "Could not load audit events.");
      showError(error.message);
    }
  }

  const attendanceInput = document.getElementById("attendance-at");
  attendanceInput.value = inputDateTime();
  document.getElementById("check-in-button").disabled = true;
  document.getElementById("check-out-button").disabled = true;

  document.getElementById("attendance-request-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const button = event.submitter || document.getElementById("check-in-button");
    const url = button.value === "check-out" ? endpoint("checkOutUrl") : endpoint("checkInUrl");
    try {
      await withPending(button, "Saving", () => requestJson(url, {
        method: "POST",
        body: new URLSearchParams(new FormData(event.currentTarget)),
      }));
      showStatus(role === "ADMIN" ? "Attendance recorded." : "Attendance request submitted.");
      attendanceInput.value = inputDateTime();
      await Promise.all([loadSelfDashboard(), loadOwnRequests(), loadRoleDashboard(), loadReport(1)]);
    } catch (error) {
      showError(error.message);
    }
  });

  reportForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    await Promise.all([loadReport(1), loadRoleDashboard()]);
    if (selectedEmployeeId) loadEmployeeSessions(selectedEmployeeId);
  });
  document.getElementById("report-previous").addEventListener("click", () => loadReport(reportPage - 1));
  document.getElementById("report-next").addEventListener("click", () => loadReport(reportPage + 1));

  const rejectForm = document.getElementById("reject-form");
  if (rejectForm) {
    rejectForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const button = event.submitter;
      const requestId = document.getElementById("reject-request-id").value;
      const body = new URLSearchParams(new FormData(event.currentTarget));
      body.delete("request_id");
      try {
        await withPending(button, "Rejecting", () => requestJson(endpointFor("rejectRequestUrl", requestId), { method: "POST", body }));
        document.getElementById("reject-dialog").close();
        showStatus("Attendance request rejected.");
        await loadRoleDashboard();
      } catch (error) {
        showError(error.message);
      }
    });

    document.getElementById("employee-history-filter").addEventListener("submit", (event) => {
      event.preventDefault();
      clearError();
      loadEmployeeSessions(document.getElementById("history-employee").value);
    });

    document.getElementById("corrected-field").addEventListener("change", (event) => {
      const value = event.currentTarget.value === "CHECK_OUT_AT" ? dialogSession.check_out_at : dialogSession.check_in_at;
      document.getElementById("correction-value").value = inputDateTime(value);
    });

    document.getElementById("correction-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const button = event.submitter;
      const sessionId = document.getElementById("correction-session-id").value;
      const body = new URLSearchParams(new FormData(event.currentTarget));
      body.delete("session_id");
      try {
        await withPending(button, "Saving", () => requestJson(endpointFor("correctSessionUrl", sessionId), { method: "POST", body }));
        showStatus("Session correction saved.");
        await refreshAfterSessionChange();
      } catch (error) {
        showError(error.message);
      }
    });

    document.getElementById("close-session-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const button = event.submitter;
      const sessionId = document.getElementById("close-session-id").value;
      const body = new URLSearchParams(new FormData(event.currentTarget));
      body.delete("session_id");
      try {
        await withPending(button, "Closing", () => requestJson(endpointFor("closeSessionUrl", sessionId), { method: "POST", body }));
        showStatus("Active session closed.");
        await refreshAfterSessionChange();
      } catch (error) {
        showError(error.message);
      }
    });

    document.querySelectorAll("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => button.closest("dialog").close());
    });
  }

  const requestFilter = document.getElementById("admin-request-filter");
  if (requestFilter) {
    requestFilter.addEventListener("submit", (event) => {
      event.preventDefault();
      clearError();
      loadAdminRequests();
    });
    document.getElementById("admin-assignment-filter").addEventListener("submit", (event) => {
      event.preventDefault();
      clearError();
      loadAdminAssignments();
    });
    document.getElementById("admin-audit-filter").addEventListener("submit", (event) => {
      event.preventDefault();
      clearError();
      loadAdminAudit();
    });

    const tabs = [...document.querySelectorAll("[data-history-tab]")];
    const selectTab = (tab) => {
      for (const item of tabs) {
        const selected = item === tab;
        item.setAttribute("aria-selected", String(selected));
        item.classList.toggle("secondary", !selected);
        document.getElementById(item.getAttribute("aria-controls")).hidden = !selected;
      }
      if (tab.dataset.historyTab === "requests") loadAdminRequests();
      if (tab.dataset.historyTab === "assignments") loadAdminAssignments();
      if (tab.dataset.historyTab === "audit") loadAdminAudit();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => selectTab(tab));
      tab.addEventListener("keydown", (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const offset = event.key === "ArrowRight" ? 1 : -1;
        const next = tabs[(index + offset + tabs.length) % tabs.length];
        next.focus();
        selectTab(next);
      });
    });
  }

  Promise.allSettled([
    loadSelfDashboard(),
    loadOwnRequests(),
    loadReport(),
    loadRoleDashboard(),
    loadAdminRequests(),
  ]);
})();
