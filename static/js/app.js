/*
 * CineSync front-end helpers.
 * Every page gets its data from the REST API (/api/...) and sends every action to it.
 *
 *   Cine.Api.get(url) / post(url, data) / put / patch / del   -> calls the API (with the CSRF token)
 *   Cine.apiTable(table, {url, columns})                      -> a DataTable filled from the API
 *   Cine.apiForm(form, {onSuccess})                           -> a form that sends JSON to the API
 *   Cine.notify(message, type)                                -> an AdminLTE alert at the top of the page
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ API calls
  function getCookie(name) {
    const match = document.cookie.split('; ').find((row) => row.startsWith(name + '='));
    return match ? decodeURIComponent(match.split('=')[1]) : '';
  }

  function errorText(data) {
    if (!data) return '';
    if (typeof data === 'string') return data;
    if (data.detail) return data.detail;
    return Object.entries(data)
      .map(([field, msgs]) => (field === 'non_field_errors' ? '' : field + ': ') + [].concat(msgs).join(' '))
      .join(' · ');
  }

  async function request(method, url, data) {
    const options = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (method !== 'GET') options.headers['X-CSRFToken'] = getCookie('csrftoken');
    if (data !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    const text = await response.text();
    let body = null;
    if (text) {
      try { body = JSON.parse(text); } catch { body = { detail: text.slice(0, 200) }; }
    }
    if (!response.ok) {
      const error = new Error(errorText(body) || response.statusText);
      error.status = response.status;
      error.data = body || {};
      throw error;
    }
    return body;
  }

  const Api = {
    get: (url) => request('GET', url),
    post: (url, data) => request('POST', url, data || {}),
    put: (url, data) => request('PUT', url, data),
    patch: (url, data) => request('PATCH', url, data),
    del: (url) => request('DELETE', url),
  };

  // ------------------------------------------------------------------ Formatting
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');

  const STATE_COLOR = {
    committed: 'success', confirmed: 'success', paid: 'success', available: 'success',
    aborted: 'danger', cancelled: 'danger',
    booked: 'secondary',
    prepared: 'warning', started: 'warning', pending: 'warning', held: 'warning',
  };
  const badge = (state, label) =>
    `<span class="badge text-bg-${STATE_COLOR[state] || 'secondary'}">${esc(label || cap(state || '—'))}</span>`;

  const vote = (v) =>
    v === true ? '<span class="badge text-bg-success">YES</span>'
      : v === false ? '<span class="badge text-bg-danger">NO</span>'
        : '<span class="badge text-bg-light border">—</span>';

  const money = (v) => Number(v || 0).toFixed(2);
  const dateTime = (iso) => (iso ? new Date(iso).toLocaleString(undefined, {
    weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  }) : '—');
  const shortId = (uuid) => 'TX-' + String(uuid).slice(0, 8).toUpperCase();
  const initials = (name) => esc((name || '?').trim().charAt(0).toUpperCase());

  // Turn a URL made with id 0 (or the zero UUID) into the URL for a real id.
  //   link('/api/customers/0/top-up/', 7)  ->  '/api/customers/7/top-up/'
  function link(template, id) {
    if (template.includes('00000000-0000-0000-0000-000000000000')) {
      return template.replace('00000000-0000-0000-0000-000000000000', id);
    }
    return template.replace('/0/', '/' + id + '/');
  }

  // For <input type="datetime-local">
  function toLocalInput(iso) {
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // ------------------------------------------------------------------ Alerts
  const ICON = { success: 'check-circle-fill', danger: 'x-circle-fill', warning: 'exclamation-triangle-fill', info: 'info-circle-fill' };
  function notify(message, type = 'success') {
    const box = document.getElementById('api-alerts');
    if (!box) { alert(message); return; }
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show`;
    div.setAttribute('role', 'alert');
    div.innerHTML = `<i class="bi bi-${ICON[type] || ICON.info} me-2"></i>${esc(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    box.prepend(div);
    if (type === 'success' || type === 'info') setTimeout(() => div.remove(), 6000);
  }

  // ------------------------------------------------------------------ Tables
  // A DataTable whose rows come from the API. Falls back to a plain table if DataTables is missing.
  function apiTable(table, { url, columns, order = [], empty = 'Nothing here yet.', onLoad }) {
    let dt = null;
    if (typeof DataTable !== 'undefined') {
      dt = new DataTable(table, {
        data: [],
        columns,
        order,
        pageLength: 10,
        lengthMenu: [5, 10, 25, 50, 100],
        autoWidth: false,
        language: { search: '', searchPlaceholder: 'Search…', emptyTable: empty, zeroRecords: 'No matching rows.' },
      });
    }

    function drawPlain(rows) {
      const body = table.tBodies[0] || table.createTBody();
      body.innerHTML = rows.length
        ? rows.map((row) => '<tr>' + columns.map((c) => {
          const value = c.data ? row[c.data] : null;
          return `<td class="${c.className || ''}">${c.render ? c.render(value, 'display', row) : esc(value)}</td>`;
        }).join('') + '</tr>').join('')
        : `<tr><td colspan="${columns.length}" class="text-center text-secondary py-4">${esc(empty)}</td></tr>`;
    }

    let currentUrl = url;
    async function reload(newUrl) {
      if (newUrl) currentUrl = newUrl;
      try {
        const rows = await Api.get(currentUrl);
        if (dt) { dt.clear(); dt.rows.add(rows); dt.draw(); } else { drawPlain(rows); }
        if (onLoad) onLoad(rows);
        return rows;
      } catch (error) {
        notify('Could not load data: ' + error.message, 'danger');
        return [];
      }
    }
    reload();
    return { table: dt, reload };
  }

  // ------------------------------------------------------------------ Forms
  function clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
    form.querySelectorAll('.invalid-feedback.api-error').forEach((el) => el.remove());
    const box = form.querySelector('.form-errors');
    if (box) { box.textContent = ''; box.classList.add('d-none'); }
  }

  function showErrors(form, data) {
    clearErrors(form);
    const general = [];
    Object.entries(data || {}).forEach(([field, messages]) => {
      const input = form.elements[field];
      const text = [].concat(messages).join(' ');
      if (input && input.classList) {
        input.classList.add('is-invalid');
        const feedback = document.createElement('div');
        feedback.className = 'invalid-feedback api-error d-block';
        feedback.textContent = text;
        (input.closest('.input-group') || input).after(feedback);
      } else {
        general.push(text);
      }
    });
    if (general.length) {
      const box = form.querySelector('.form-errors');
      if (box) { box.textContent = general.join(' '); box.classList.remove('d-none'); } else { notify(general.join(' '), 'danger'); }
    }
  }

  function formData(form) {
    const data = {};
    Array.from(form.elements).forEach((el) => {
      if (!el.name || el.disabled) return;
      if (el.type === 'checkbox') data[el.name] = el.checked;
      else if (el.type === 'radio') { if (el.checked) data[el.name] = el.value; }
      else if (el.value !== '') data[el.name] = el.value;
    });
    return data;
  }

  function fillForm(form, values) {
    clearErrors(form);
    Array.from(form.elements).forEach((el) => {
      if (!el.name || !(el.name in values)) return;
      const v = values[el.name];
      if (el.type === 'checkbox') el.checked = !!v;
      else if (el.type === 'datetime-local') el.value = v ? toLocalInput(v) : '';
      else el.value = v ?? '';
    });
  }

  // <form data-url="/api/movies/" data-method="POST">: sends JSON to the API.
  function apiForm(form, { onSuccess, getData } = {}) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = form.querySelector('[type=submit]');
      const label = button ? button.innerHTML : '';
      if (button) { button.disabled = true; button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Working…'; }
      try {
        const data = getData ? getData(form) : formData(form);
        const result = await request(form.dataset.method || 'POST', form.dataset.url, data);
        clearErrors(form);
        if (onSuccess) await onSuccess(result, form);
      } catch (error) {
        if (error.status === 400) showErrors(form, error.data);
        else notify(error.message, 'danger');
      } finally {
        if (button) { button.disabled = false; button.innerHTML = label; }
      }
    });
  }

  async function confirmDelete(url, label, onDone) {
    if (!window.confirm(`Delete ${label}? This can't be undone.`)) return;
    try {
      await Api.del(url);
      notify(`${label} was deleted.`);
      if (onDone) onDone();
    } catch (error) {
      notify(error.message, 'danger');
    }
  }

  const modal = (el) => bootstrap.Modal.getOrCreateInstance(el);

  window.Cine = {
    Api, esc, cap, badge, vote, money, dateTime, shortId, initials, link, toLocalInput,
    notify, apiTable, apiForm, formData, fillForm, clearErrors, showErrors, confirmDelete, modal,
  };
})();
