document.addEventListener("DOMContentLoaded", async () => {
  const user = await ensureAuthenticated();
  if (!user) return;

  const page = document.body.dataset.page;
  if (page === "management" && user.role !== "management") {
    window.location.replace("/management/login");
    return;
  }
  if (page === "student-reports" && user.role === "management") {
    window.location.replace("/management/dashboard");
    return;
  }
  if (page === "dashboard" && user.role === "management") {
    window.location.replace("/management/dashboard");
    return;
  }


  const nameTarget = document.getElementById("userName");
  if (nameTarget) {
    nameTarget.textContent = user.full_name || user.email || "User";
  }
  document.getElementById("welcomeName")?.replaceChildren(document.createTextNode(user.full_name || "Student"));
  const profileEmail = document.getElementById("profileEmail");
  if (profileEmail) profileEmail.textContent = user.email || "";

  const logoutButton = document.getElementById("logoutButton");
  if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
      try {
        await apiFetch("/api/auth/logout", { method: "POST" });
      } catch (error) {
        console.warn("Logout warning:", error);
      } finally {
        window.location.href = user.role === "management" ? "/management/login" : "/login";
      }
    });
  }

  if (page === "dashboard") {
    initDashboard(user);
  } else if (page === "student-reports") {
    initStudentReports();
  } else if (page === "management") {
    initManagement();
  } else if (page === "profile") {
    initProfile(user);
  }
});

async function ensureAuthenticated() {
  try {
    const response = await apiFetch("/api/auth/me");
    if (!response.success) {
      window.location.href = "/login";
      return null;
    }
    return response.user;
  } catch (error) {
    console.warn("Auth check failed:", error);
    window.location.href = "/login";
    return null;
  }
}

function setMessage(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.style.color = isError ? "var(--red)" : "var(--green)";
  element.style.display = message ? "block" : "none";
}

async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };

  if (!(options.body instanceof FormData) && method !== "GET" && method !== "HEAD") {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const response = await fetch(url, {
    ...options,
    method,
    headers,
    body: options.body && typeof options.body !== "string" && !(options.body instanceof FormData)
      ? JSON.stringify(options.body)
      : options.body,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof data === "string" ? data : (data.message || "Request failed.");
    throw new Error(message);
  }

  return data;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(value) {
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString();
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusBadge(status) {
  const normalized = String(status || "Submitted").trim();
  return normalized.replace(/\s+/g, "-").toLowerCase();
}

function renderStatusBadge(status) {
  const value = status || "Submitted";
  return `<span class="badge ${statusBadge(value)}">${escapeHtml(value)}</span>`;
}

async function initDashboard(user) {
  const statsContainer = document.getElementById("statsGrid");
  const recentReportsContainer = document.getElementById("recentReports");
  const notificationsContainer = document.getElementById("notifications");
  const markReadButton = document.getElementById("markNotificationsRead");
  const reportsBody = document.getElementById("dashboardReportsBody");
  const reportSearch = document.getElementById("dashboardReportSearch");
  const reportStatus = document.getElementById("dashboardReportStatus");
  const reportCount = document.getElementById("dashboardReportCount");
  const detailPanel = document.getElementById("dashboardReportDetail");
  let reports = [];

  if (markReadButton && markReadButton.dataset.bound !== "true") {
    markReadButton.dataset.bound = "true";
    markReadButton.addEventListener("click", async () => {
      markReadButton.disabled = true;
      try {
        await apiFetch("/api/notifications", { method: "POST" });
        await initDashboard(user);
      } catch (error) {
        markReadButton.disabled = false;
        markReadButton.title = error.message;
      }
    });
  }

  try {
    const dashboardData = await apiFetch("/api/reports");
    const notificationsData = await apiFetch("/api/notifications");
    reports = dashboardData.reports || [];

    const counts = {
      total: reports.length,
      submitted: reports.filter((item) => item.status === "Submitted").length,
      review: reports.filter((item) => ["Under Review", "Investigating"].includes(item.status)).length,
      assigned: reports.filter((item) => item.status === "Assigned").length,
      resolved: reports.filter((item) => item.status === "Resolved").length,
      closed: reports.filter((item) => item.status === "Closed").length,
    };

    statsContainer.innerHTML = `
      ${renderStat("Total Reports", counts.total, "total")}
      ${renderStat("Submitted", counts.submitted, "submitted")}
      ${renderStat("In Review", counts.review, "review")}
      ${renderStat("Assigned", counts.assigned, "assigned")}
      ${renderStat("Resolved", counts.resolved, "resolved")}
      ${renderStat("Closed", counts.closed, "closed")}
    `;

    if (!reports.length) {
      recentReportsContainer.innerHTML = '<div class="empty-state">No reports available yet.</div>';
    } else {
      recentReportsContainer.innerHTML = reports.slice(0, 5).map((report) => `
        <div class="report-item">
          <div class="report-header">
            <h3 class="report-title">${escapeHtml(report.report_id || report.title)}</h3>
            ${renderStatusBadge(report.status)}
          </div>
          <p>${escapeHtml(report.title)}</p>
          <small>${escapeHtml(report.campus_location || "Campus location not set")} · ${formatDate(report.updated_at)}</small>
        </div>
      `).join("");
    }

    const renderMyReports = () => {
      const query = (reportSearch?.value || "").trim().toLowerCase();
      const status = reportStatus?.value || "all";
      const filtered = reports.filter((report) => {
        const text = `${report.report_id} ${report.category} ${report.campus_location}`.toLowerCase();
        return (!query || text.includes(query)) && (status === "all" || report.status === status);
      });
      if (reportCount) reportCount.textContent = `${filtered.length} of ${reports.length}`;
      reportsBody.innerHTML = filtered.length ? filtered.map((report) => `
        <tr>
          <td>${escapeHtml(report.report_id)}</td>
          <td>${escapeHtml(report.category)}</td>
          <td>${escapeHtml(report.campus_location)}</td>
          <td>${formatDate(report.incident_date)}</td>
          <td>${renderStatusBadge(report.status)}</td>
          <td><button type="button" class="secondary-btn" data-dashboard-view="${report.id}">View</button></td>
        </tr>
      `).join("") : '<tr><td colspan="6" class="empty-state">No reports match your search.</td></tr>';
      reportsBody.querySelectorAll("button[data-dashboard-view]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            const result = await apiFetch(`/api/reports/${button.dataset.dashboardView}`);
            renderStudentReportDetail(detailPanel, result);
          } catch (error) {
            detailPanel.hidden = false;
            detailPanel.textContent = error.message;
          }
        });
      });
    };
    if (reportSearch && reportSearch.dataset.bound !== "true") {
      reportSearch.dataset.bound = "true";
      reportSearch.addEventListener("input", renderMyReports);
    }
    if (reportStatus && reportStatus.dataset.bound !== "true") {
      reportStatus.dataset.bound = "true";
      reportStatus.addEventListener("change", renderMyReports);
    }
    renderMyReports();

    const notifications = notificationsData.notifications || [];
    const unreadCount = notifications.filter((item) => !item.is_read).length;
    if (markReadButton) {
      markReadButton.disabled = unreadCount === 0;
      markReadButton.textContent = unreadCount ? `Mark ${unreadCount} read` : "All caught up";
    }
    notificationsContainer.innerHTML = notifications.length
      ? notifications.slice(0, 6).map((item) => `
          <button type="button" class="notification-item${item.is_read ? "" : " unread"} notification-button" data-notification-id="${item.id}" data-report-id="${item.report_id || ""}">
            <span class="notification-title">${escapeHtml(item.message)}</span>
            <span class="notification-meta">${item.report_id ? `Report ${escapeHtml(item.report_id)}` : "System update"}</span>
            <small>${formatDate(item.created_at)}${item.is_read ? " · Read" : " · Unread"}</small>
          </button>
        `).join("")
      : '<div class="empty-state">No notifications.</div>';

    notificationsContainer.querySelectorAll(".notification-button").forEach((element) => {
      element.addEventListener("click", async () => {
        const notificationId = Number(element.dataset.notificationId);
        const reportId = element.dataset.reportId;
        await markNotificationAsRead(notificationId, reportId, "student");
        await initDashboard(user);
      });
    });
  } catch (error) {
    if (statsContainer) statsContainer.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (recentReportsContainer) recentReportsContainer.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    if (notificationsContainer) notificationsContainer.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderStat(label, value, tone = "total") {
  return `<div class="card stat-box stat-${tone}"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value">${value}</div></div>`;
}

async function triggerNotificationReport(reportId, role = "student") {
  if (!reportId) return;
  const openTargets = [];
  if (role === "management") {
    const listItems = document.querySelectorAll("article[data-report-id]");
    listItems.forEach((article) => {
      const articleId = Number(article.dataset.reportId);
      if (articleId === Number(reportId)) openTargets.push(article);
    });
  } else {
    const reportButtons = document.querySelectorAll("button[data-dashboard-view]");
    reportButtons.forEach((button) => {
      if (Number(button.dataset.dashboardView) === Number(reportId)) openTargets.push(button);
    });
  }

  if (!openTargets.length) {
    if (role === "student") {
      const detailPanel = document.getElementById("dashboardReportDetail");
      if (detailPanel && document.body.dataset.page === "dashboard") {
        try {
          const detail = await apiFetch(`/api/reports/${reportId}`);
          renderStudentReportDetail(detailPanel, detail);
          detailPanel.scrollIntoView({ behavior: "smooth", block: "center" });
          detailPanel.classList.add("report-highlight");
          window.setTimeout(() => detailPanel.classList.remove("report-highlight"), 2200);
        } catch (error) {
          setMessage(detailPanel, error.message, true);
          detailPanel.hidden = false;
        }
      } else {
        window.location.href = "/reports";
      }
    }
    return;
  }

  const target = openTargets[0];
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("report-highlight");
  window.setTimeout(() => target.classList.remove("report-highlight"), 2200);

  if (role === "management") {
    const details = target.querySelector("details");
    if (details) details.setAttribute("open", "open");
    const updateButton = target.querySelector("button[data-action='update']");
    if (updateButton) updateButton.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }

  target.click();
}

async function markNotificationAsRead(notificationId, reportId, role = "student") {
  if (!notificationId) return;
  try {
    await apiFetch(`/api/notifications/${notificationId}/read`, { method: "POST" });
    if (reportId) {
      await triggerNotificationReport(reportId, role);
    }
  } catch (error) {
    console.warn("Notification read failed:", error.message);
  }
}

function renderStudentReportDetail(panel, result) {
  const report = result.report || result;
  const history = result.status_history || [];
  const responses = result.responses || [];
  panel.innerHTML = `
    <div class="section-heading">
      <div><p class="eyebrow">REPORT DETAILS</p><h2>${escapeHtml(report.report_id)}</h2></div>
      ${renderStatusBadge(report.status)}
    </div>
    <p><strong>${escapeHtml(report.category)}</strong> · ${escapeHtml(report.campus_location)}</p>
    <p>${escapeHtml(report.description)}</p>
    <p><strong>Action Taken:</strong> ${escapeHtml(report.action_details || "No action recorded yet.")}</p>
    <h3>Management Responses</h3>
    ${responses.length ? responses.map((item) => `<div class="notification-item"><strong>${escapeHtml(item.responder_name || "Management")}</strong><div>${escapeHtml(item.message)}</div><small>${formatDate(item.created_at)}</small></div>`).join("") : '<div class="empty-state">No response yet.</div>'}
    <h3>Status History</h3>
    ${history.length ? history.map((item) => `<div class="notification-item"><strong>${escapeHtml(item.old_status || "Created")} → ${escapeHtml(item.new_status)}</strong><div>${escapeHtml(item.notes || "No notes")}</div><small>${formatDate(item.created_at)}</small></div>`).join("") : '<div class="empty-state">No status history yet.</div>'}
    <a href="/reports">Open full report view</a>
  `;
  panel.hidden = false;
}

async function initStudentReports() {
  const reportForm = document.getElementById("reportForm");
  const reportMessage = document.getElementById("reportMessage");
  const tableBody = document.getElementById("studentReportsBody");
  const cancelButton = document.getElementById("cancelEdit");
  const detailPanel = document.getElementById("studentReportDetail");
  let editingId = null;

  const resetForm = () => {
    reportForm.reset();
    editingId = null;
    cancelButton.hidden = true;
    document.getElementById("formTitle").textContent = "Create Safety Report";
    reportForm.querySelector("button[type='submit']").textContent = "Submit Safety Report";
    document.getElementById("reportCategory").value = "Safety";
    document.getElementById("reportSeverity").value = "Medium";
  };

  const renderDetail = (report) => {
    if (!report) {
      detailPanel.style.display = "none";
      return;
    }

    const history = report.status_history || [];
    const responses = report.responses || [];

    detailPanel.innerHTML = `
      <h2>Report Details</h2>
      <div class="report-header">
        <div>
          <strong>${escapeHtml(report.report_id)}</strong>
          <div class="muted">${escapeHtml(report.title)}</div>
        </div>
        ${renderStatusBadge(report.status)}
      </div>
      <div class="form-grid">
        <div class="form-group"><label>Category</label><div>${escapeHtml(report.category || "Safety")}</div></div>
        <div class="form-group"><label>Location</label><div>${escapeHtml(report.campus_location || "—")}</div></div>
        <div class="form-group"><label>Date &amp; Time</label><div>${escapeHtml(report.incident_date || "—")} ${escapeHtml(report.incident_time || "")}</div></div>
        <div class="form-group"><label>Severity</label><div>${escapeHtml(report.severity || "—")}</div></div>
      </div>
      <p><strong>Description:</strong> ${escapeHtml(report.description || "No description provided.")}</p>
      <p><strong>Action Taken:</strong> ${escapeHtml(report.action_details || "No action recorded yet.")}</p>
      <h3>Evidence</h3>
      ${(report.evidence_files || []).length ? report.evidence_files.map((filename) => `
        <a class="evidence-link" href="/api/reports/${report.id}/evidence/${encodeURIComponent(filename)}" target="_blank" rel="noopener">${escapeHtml(filename)}</a>
      `).join("") : '<div class="empty-state">No evidence attached.</div>'}
      <h3>Status History</h3>
      ${history.length ? history.map((item) => `
        <div class="notification-item">
          <strong>${escapeHtml(item.new_status)}</strong>
          <div>${escapeHtml(item.notes || "No notes")}</div>
          <small>${escapeHtml(item.changed_by_name || "System")} · ${formatDate(item.created_at)}</small>
        </div>
      `).join("") : '<div class="empty-state">No status history yet.</div>'}
      <h3>Management Responses</h3>
      ${responses.length ? responses.map((item) => `
        <div class="notification-item">
          <strong>${escapeHtml(item.responder_name || "Management")}</strong>
          <div>${escapeHtml(item.message)}</div>
          <small>${formatDate(item.created_at)}</small>
        </div>
      `).join("") : '<div class="empty-state">No management response yet.</div>'}
    `;
    detailPanel.style.display = "block";
  };

  const renderReports = async () => {
    try {
      const data = await apiFetch("/api/reports");
      const rows = data.reports || [];
      if (!rows.length) {
        tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No reports submitted yet.</td></tr>';
        detailPanel.style.display = "none";
        return;
      }

      tableBody.innerHTML = rows.map((report) => `
        <tr>
          <td>${escapeHtml(report.report_id || "—")}</td>
          <td>${escapeHtml(report.title)}</td>
          <td>${escapeHtml(report.category || "Safety")}</td>
          <td>${renderStatusBadge(report.status)}</td>
          <td>${escapeHtml(report.severity || "—")}</td>
          <td>${formatDate(report.updated_at)}</td>
          <td>
            <button type="button" class="secondary-btn" data-action="view" data-id="${report.id}">View</button>
            ${report.status === "Submitted" ? `
              <button type="button" class="secondary-btn" data-action="edit" data-id="${report.id}">Edit</button>
              <button type="button" class="danger-btn" data-action="delete" data-id="${report.id}">Delete</button>
            ` : ""}
          </td>
        </tr>
      `).join("");

      tableBody.querySelectorAll("button[data-action='view']").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            const result = await apiFetch(`/api/reports/${button.dataset.id}`);
            renderDetail({
              ...(result.report || result),
              status_history: result.status_history || [],
              responses: result.responses || [],
            });
          } catch (error) {
            setMessage(reportMessage, error.message, true);
          }
        });
      });

      tableBody.querySelectorAll("button[data-action='edit']").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            const report = await apiFetch(`/api/reports/${button.dataset.id}`);
            const item = report.report || report;
            editingId = item.id;
            document.getElementById("formTitle").textContent = "Edit Safety Report";
            reportForm.querySelector("button[type='submit']").textContent = "Save Changes";
            cancelButton.hidden = false;
            document.getElementById("reportCategory").value = item.category || "Safety";
            document.getElementById("campusLocation").value = item.campus_location || "";
            document.getElementById("incidentDateTime").value = item.incident_date && item.incident_time
              ? `${item.incident_date}T${item.incident_time.slice(0, 5)}`
              : "";
            document.getElementById("reportSeverity").value = item.severity || "Medium";
            document.getElementById("reportDescription").value = item.description || "";
            setMessage(reportMessage, "Editing report. Update and save changes.");
            window.scrollTo({ top: 0, behavior: "smooth" });
          } catch (error) {
            setMessage(reportMessage, error.message, true);
          }
        });
      });

      tableBody.querySelectorAll("button[data-action='delete']").forEach((button) => {
        button.addEventListener("click", async () => {
          const id = Number(button.dataset.id);
          if (!window.confirm("Delete this report?")) return;
          try {
            await apiFetch(`/api/reports/${id}`, { method: "DELETE" });
            setMessage(reportMessage, "Report deleted successfully.");
            await renderReports();
          } catch (error) {
            setMessage(reportMessage, error.message, true);
          }
        });
      });
    } catch (error) {
      tableBody.innerHTML = `<tr><td colspan="7">${escapeHtml(error.message)}</td></tr>`;
    }
  };

  cancelButton.addEventListener("click", () => {
    resetForm();
    setMessage(reportMessage, "Form reset.");
  });

  reportForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = reportForm.querySelector("button[type='submit']");
    const wasEditing = Boolean(editingId);
    submitButton.disabled = true;
    submitButton.textContent = wasEditing ? "Saving..." : "Submitting...";

    try {
      const formData = new FormData(reportForm);

      if (editingId) {
        await apiFetch(`/api/reports/${editingId}`, {
          method: "PATCH",
          body: formData,
        });
        setMessage(reportMessage, "Report updated successfully.");
      } else {
        const result = await apiFetch("/api/reports", {
          method: "POST",
          body: formData,
        });
        setMessage(reportMessage, `Report submitted successfully. Report ID: ${result.report.report_id}`);
      }

      resetForm();
      await renderReports();
    } catch (error) {
      setMessage(reportMessage, error.message, true);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = editingId ? "Save Changes" : "Submit Safety Report";
    }
  });

  resetForm();
  await renderReports();
}

async function initManagement() {
  const filter = document.getElementById("statusFilter");
  const severityFilter = document.getElementById("severityFilter");
  const searchInput = document.getElementById("searchInput");
  const reportList = document.getElementById("managementReportList");
  const managementMessage = document.getElementById("managementMessage");
  const statsContainer = document.getElementById("managementStats");
  const notificationsContainer = document.getElementById("managementNotifications");
  const reportCount = document.getElementById("managementReportCount");
  const markReadButton = document.getElementById("managementMarkNotificationsRead");

  const modal = document.getElementById("managementReportModal") || (() => {
    const element = document.createElement("div");
    element.id = "managementReportModal";
    element.className = "report-modal hidden";
    document.body.appendChild(element);
    return element;
  })();

  const closeModal = () => {
    modal.classList.add("hidden");
    modal.classList.remove("visible");
    modal.innerHTML = "";
  };

  const openReportModal = async (reportId) => {
    try {
      const detail = await apiFetch(`/api/reports/${reportId}`);
      const report = detail.report || detail;
      const statusOptions = [
        "Submitted",
        "Under Review",
        "Assigned",
        "Investigating",
        "Action Taken",
        "Resolved",
        "Closed",
      ].map((status) => `
        <option value="${status}" ${status === (report.status || "Submitted") ? "selected" : ""}>${status}</option>
      `).join("");
      const history = (detail.status_history || []).map((entry) => `
        <div class="notification-item">
          <strong>${escapeHtml(entry.old_status || "Created")} → ${escapeHtml(entry.new_status)}</strong>
          <div>${escapeHtml(entry.notes || "No notes")}</div>
          <small>${escapeHtml(entry.changed_by_name || "System")} · ${formatDate(entry.created_at)}</small>
        </div>
      `).join("") || '<div class="empty-state">No status history recorded.</div>';
      const responses = (detail.responses || []).map((response) => `
        <div class="notification-item">
          <strong>${escapeHtml(response.responder_name || "Management")}</strong>
          <div>${escapeHtml(response.message)}</div>
          <small>${formatDate(response.created_at)}</small>
        </div>
      `).join("") || '<div class="empty-state">No responses yet.</div>';
      const evidence = (report.evidence_files || []).map((filename) => `
        <a class="evidence-link" href="/api/reports/${report.id}/evidence/${encodeURIComponent(filename)}" target="_blank" rel="noopener">${escapeHtml(filename)}</a>
      `).join("") || '<span class="muted-text">No evidence attached.</span>';

      modal.innerHTML = `
        <div class="report-modal-backdrop" data-close-modal="true"></div>
        <div class="report-modal-card" role="dialog" aria-modal="true" aria-labelledby="managementDetailTitle">
          <div class="report-modal-header">
            <div>
              <p class="eyebrow">REPORT DETAILS</p>
              <h2 id="managementDetailTitle">${escapeHtml(report.report_id || report.title)}</h2>
            </div>
            <button type="button" class="secondary-btn" data-close-modal="true">Close</button>
          </div>
          <div class="report-modal-body">
            <div class="report-summary-grid">
              <div><strong>Category:</strong> ${escapeHtml(report.category || "Safety")}</div>
              <div><strong>Location:</strong> ${escapeHtml(report.campus_location || "Not provided")}</div>
              <div><strong>Severity:</strong> ${escapeHtml(report.severity || "Medium")}</div>
              <div><strong>Reported:</strong> ${escapeHtml(report.incident_date || "Not provided")} ${escapeHtml(report.incident_time || "")}</div>
              <div><strong>Status:</strong> ${renderStatusBadge(report.status)}</div>
              <div><strong>Student:</strong> ${escapeHtml(report.student_name || "Student")} · ${escapeHtml(report.student_email || "")}</div>
            </div>

            <div class="detail-section">
              <h3>Report Information</h3>
              <p><strong>Title:</strong> ${escapeHtml(report.title || "Safety report")}</p>
              <p><strong>Description:</strong> ${escapeHtml(report.description || "No description provided.")}</p>
              <p><strong>Evidence:</strong> ${evidence}</p>
            </div>

            <div class="detail-section">
              <h3>Management Actions</h3>
              <div class="form-grid">
                <div class="form-group full-width">
                  <label>Status</label>
                  <select id="modalStatusSelect">
                    ${statusOptions}
                  </select>
                </div>
                <div class="form-group full-width">
                  <label>Action Taken</label>
                  <textarea id="modalActionDetails">${escapeHtml(report.action_details || "")}</textarea>
                </div>
                <div class="form-group full-width">
                  <label>Response</label>
                  <textarea id="modalResponse">${escapeHtml(report.management_response || "")}</textarea>
                </div>
              </div>
              <div class="status-actions">
                <button type="button" class="primary-btn" id="saveManagementUpdate">Save Update</button>
                <button type="button" class="secondary-btn" id="resolveManagementReport">Resolve</button>
                <button type="button" class="secondary-btn" id="closeManagementReport">Close</button>
              </div>
            </div>

            <div class="detail-section">
              <h3>Status History</h3>
              ${history}
            </div>

            <div class="detail-section">
              <h3>Responses</h3>
              ${responses}
            </div>
          </div>
        </div>
      `;

      modal.classList.remove("hidden");
      modal.classList.add("visible");

      modal.querySelector("[data-close-modal='true']")?.addEventListener("click", closeModal);
      const saveButton = document.getElementById("saveManagementUpdate");
      const resolveButton = document.getElementById("resolveManagementReport");
      const closeButton = document.getElementById("closeManagementReport");
      const statusSelect = document.getElementById("modalStatusSelect");
      const actionDetailsField = document.getElementById("modalActionDetails");
      const responseField = document.getElementById("modalResponse");

      saveButton?.addEventListener("click", async () => {
        try {
          saveButton.disabled = true;
          saveButton.textContent = "Saving...";
          await apiFetch(`/api/reports/${report.id}/management`, {
            method: "POST",
            body: {
              status: statusSelect?.value || report.status || "Submitted",
              action_details: actionDetailsField?.value || "",
              management_response: responseField?.value || "",
            },
          });
          setMessage(managementMessage, "Report update saved.");
          closeModal();
          await renderReports();
        } catch (error) {
          setMessage(managementMessage, error.message, true);
        } finally {
          if (saveButton) {
            saveButton.disabled = false;
            saveButton.textContent = "Save Update";
          }
        }
      });

      resolveButton?.addEventListener("click", async () => {
        try {
          resolveButton.disabled = true;
          if (statusSelect) statusSelect.value = "Resolved";
          await apiFetch(`/api/reports/${report.id}/management`, {
            method: "POST",
            body: {
              status: "Resolved",
              action_details: actionDetailsField?.value || "",
              management_response: responseField?.value || "",
            },
          });
          setMessage(managementMessage, "Report marked as resolved.");
          closeModal();
          await renderReports();
        } catch (error) {
          setMessage(managementMessage, error.message, true);
        } finally {
          resolveButton.disabled = false;
        }
      });

      closeButton?.addEventListener("click", async () => {
        try {
          closeButton.disabled = true;
          if (statusSelect) statusSelect.value = "Closed";
          await apiFetch(`/api/reports/${report.id}/management`, {
            method: "POST",
            body: {
              status: "Closed",
              action_details: actionDetailsField?.value || "",
              management_response: responseField?.value || "",
            },
          });
          setMessage(managementMessage, "Report closed.");
          closeModal();
          await renderReports();
        } catch (error) {
          setMessage(managementMessage, error.message, true);
        } finally {
          closeButton.disabled = false;
        }
      });
    } catch (error) {
      setMessage(managementMessage, error.message, true);
    }
  };

  if (markReadButton && markReadButton.dataset.bound !== "true") {
    markReadButton.dataset.bound = "true";
    markReadButton.addEventListener("click", async () => {
      markReadButton.disabled = true;
      try {
        await apiFetch("/api/notifications", { method: "POST" });
        await renderReports();
      } catch (error) {
        markReadButton.disabled = false;
        setMessage(managementMessage, error.message, true);
      }
    });
  }

  const renderReports = async () => {
    try {
      const [data, notificationData] = await Promise.all([
        apiFetch("/api/reports"),
        apiFetch("/api/notifications"),
      ]);
      const allReports = data.reports || [];
      const counts = {
        total: allReports.length,
        submitted: allReports.filter((report) => report.status === "Submitted").length,
        review: allReports.filter((report) => report.status === "Under Review").length,
        assigned: allReports.filter((report) => report.status === "Assigned").length,
        resolved: allReports.filter((report) => report.status === "Resolved").length,
        closed: allReports.filter((report) => report.status === "Closed").length,
      };
      statsContainer.innerHTML = `
        ${renderStat("Total Reports", counts.total, "total")}
        ${renderStat("Submitted", counts.submitted, "submitted")}
        ${renderStat("Under Review", counts.review, "review")}
        ${renderStat("Assigned", counts.assigned, "assigned")}
        ${renderStat("Resolved", counts.resolved, "resolved")}
        ${renderStat("Closed", counts.closed, "closed")}
      `;

      const notifications = notificationData.notifications || [];
      const unreadCount = notifications.filter((item) => !item.is_read).length;
      if (markReadButton) {
        markReadButton.disabled = unreadCount === 0;
        markReadButton.textContent = unreadCount ? `Mark ${unreadCount} read` : "All caught up";
      }
      notificationsContainer.innerHTML = notifications.length ? notifications.slice(0, 10).map((item) => `
        <button type="button" class="notification-item${item.is_read ? "" : " unread"} notification-button" data-notification-id="${item.id}" data-report-id="${item.report_id || ""}">
          <span class="notification-title">${escapeHtml(item.message)}</span>
          <span class="notification-meta">${item.report_id ? `Report ${escapeHtml(item.report_id)}` : "System update"}</span>
          <small>${formatDate(item.created_at)}${item.is_read ? " · Read" : " · Unread"}</small>
        </button>
      `).join("") : '<div class="empty-state">No notifications.</div>';
      notificationsContainer.querySelectorAll(".notification-button").forEach((element) => {
        element.addEventListener("click", async () => {
          const notificationId = Number(element.dataset.notificationId);
          const reportId = element.dataset.reportId;
          await markNotificationAsRead(notificationId, reportId, "management");
          if (reportId) await openReportModal(Number(reportId));
          await renderReports();
        });
      });

      let reports = allReports;
      const statusFilter = filter.value;
      const severityValue = severityFilter?.value || "all";
      const search = searchInput.value.trim().toLowerCase();

      reports = reports.filter((report) => {
        const matchesStatus = statusFilter === "all" || report.status === statusFilter;
        const matchesSeverity = severityValue === "all" || report.severity === severityValue;
        const haystack = `${report.report_id} ${report.title} ${report.description} ${report.category} ${report.campus_location} ${report.student_name || ""} ${report.student_email || ""}`.toLowerCase();
        const matchesSearch = !search || haystack.includes(search);
        return matchesStatus && matchesSeverity && matchesSearch;
      });

      if (reportCount) reportCount.textContent = `${reports.length} of ${allReports.length}`;
      if (!reports.length) {
        reportList.innerHTML = '<div class="empty-state">No reports match the current filters.</div>';
        return;
      }

      reportList.innerHTML = reports.map((report) => `
        <article class="management-report-card card" data-report-id="${report.id}">
          <div class="management-card-top">
            <div>
              <p class="eyebrow">REPORT</p>
              <h3>${escapeHtml(report.report_id || report.title)}</h3>
            </div>
            ${renderStatusBadge(report.status)}
          </div>
          <div class="management-card-meta">
            <span><strong>Category:</strong> ${escapeHtml(report.category || "Safety")}</span>
            <span><strong>Location:</strong> ${escapeHtml(report.campus_location || "Not provided")}</span>
            <span><strong>Severity:</strong> ${escapeHtml(report.severity || "Medium")}</span>
            <span><strong>Date:</strong> ${escapeHtml(report.incident_date || "Not provided")}</span>
            <span><strong>Time:</strong> ${escapeHtml(report.incident_time || "Not provided")}</span>
          </div>
          <div class="status-actions">
            <button class="primary-btn" type="button" data-action="view" data-report-id="${report.id}">View</button>
          </div>
        </article>
      `).join("");

      reportList.querySelectorAll("button[data-action='view']").forEach((button) => {
        button.addEventListener("click", async () => {
          await openReportModal(Number(button.dataset.reportId));
        });
      });
    } catch (error) {
      reportList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  };

  filter.addEventListener("change", renderReports);
  severityFilter?.addEventListener("change", renderReports);
  searchInput.addEventListener("input", renderReports);
  await renderReports();
}

async function initProfile(user) {
  const fullNameInput = document.getElementById("profileFullName");
  const emailInput = document.getElementById("profileEmail");
  const roleInput = document.getElementById("profileRole");
  const messageBox = document.getElementById("profileMessage");
  const saveButton = document.getElementById("saveProfileButton");

  if (!fullNameInput || !emailInput || !roleInput || !saveButton) return;

  document.querySelectorAll(".nav-link").forEach((link) => {
    const managementLink = link.getAttribute("href")?.startsWith("/management");
    link.hidden = user.role === "management" ? !managementLink : managementLink;
  });

  const loadProfile = async () => {
    try {
      const profileData = await apiFetch("/api/auth/profile");
      fullNameInput.value = profileData.user.full_name || "";
      emailInput.value = profileData.user.email || "";
      roleInput.value = profileData.user.role ? profileData.user.role.charAt(0).toUpperCase() + profileData.user.role.slice(1) : "Student";
    } catch (error) {
      setMessage(messageBox, error.message, true);
    }
  };

  saveButton.addEventListener("click", async () => {
    const payload = {
      full_name: fullNameInput.value.trim(),
      email: emailInput.value.trim(),
    };
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
      const response = await apiFetch("/api/auth/profile", {
        method: "PATCH",
        body: payload,
      });
      setMessage(messageBox, response.message || "Profile updated successfully.");
      document.getElementById("userName").textContent = response.user.full_name || user.full_name || "User";
      await loadProfile();
    } catch (error) {
      setMessage(messageBox, error.message, true);
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = "Save Profile";
    }
  });

  await loadProfile();
}
