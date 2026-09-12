// Publish: the steps from saved to live, each an explicit click. Not
// committed lists what the admin saved since the last commit and commits
// exactly that; Not live checks GitHub and shows everything a push would
// publish; Published is this computer's log of commits and publishes.
// topbar() adds the "saved, not committed" chip to the top bar.
import { api } from "../lib/api.js";
import { h, clear, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast, guard, announce } from "../lib/ui.js";

const TABS = [
  { sub: "", label: "Not committed" },
  { sub: "live", label: "Not live" },
  { sub: "log", label: "Published" },
];
const CHANGE = { added: "Added", modified: "Changed", deleted: "Removed" };
const KINDS = [["pages", "Pages"], ["images", "Images"], ["video", "Video"], ["code", "Scripts and styles"], ["other", "Other files"]];

function when(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "";
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function bytes(n) {
  if (n === null || n === undefined) return "";
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
  if (n >= 1024) return Math.round(n / 1024) + " KB";
  return n + " bytes";
}

const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

// A file under flow/ is served by the local preview at the same path less
// "flow", so a changed photo can be shown as it is on this computer now.
const previewUrl = (path) => "/" + path.replace(/^flow\//, "");

function pathRow(it, extra) {
  return h("li", {}, h("span", { class: "badge outline" }, CHANGE[it.change] || it.change),
    h("span", { class: "pub-path" }, it.path), extra || null,
    it.bytes !== undefined && it.change !== "deleted" ? h("span", { class: "pub-size" }, bytes(it.bytes)) : null);
}

export async function render(main, { sub, app }) {
  useCss("publish");
  guard.clear();
  const tab = TABS.find((t) => t.sub === (sub || "").split("/")[0]) || TABS[0];
  const body = h("div", { class: "pub-body" });
  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("h1", { tabindex: "-1" }, "Publish"),
      h("p", { class: "sub" }, "A save shows on this computer's preview at once. Committing records the saved files in the repository; publishing sends the commits to GitHub, and the Netlify site and GitHub Pages deploy from there."))),
    h("nav", { class: "pub-tabs", "aria-label": "Publish steps" }, TABS.map((t) =>
      h("a", { href: "#/publish" + (t.sub ? "/" + t.sub : ""), class: "pub-tab" + (t === tab ? " on" : ""), "aria-current": t === tab ? "page" : null }, t.label))),
    body);
  if (tab.sub === "live") return notLive(body, app);
  if (tab.sub === "log") return publishedLog(body);
  return notCommitted(body, app);
}

// ---- the top bar chip ---------------------------------------------------------

let chipEl = null;

async function refreshChip() {
  if (!chipEl) return;
  let s;
  try { s = await api("GET", "publish/summary"); } catch (e) { return; }
  const saved = s.saved || s.generated;
  if (saved) {
    chipEl.textContent = saved + " saved, not committed";
    chipEl.title = "Saved on this computer but not in a commit yet. Open Publish to review and commit.";
  } else if (s.ahead) {
    chipEl.textContent = plural(s.ahead, "commit", "commits") + " not live";
    chipEl.title = "Committed but not sent to GitHub, as of the last check. Open Publish to review and publish.";
  }
  chipEl.hidden = !(saved || s.ahead);
}

export function topbar(app) {
  if (chipEl || !app.topSlot) return;
  useCss("publish");
  chipEl = h("a", { class: "chip pub-chip", href: "#/publish", hidden: true });
  app.topSlot.append(chipEl);
  // git status only when something was saved, or twice a minute for edits
  // made outside the admin; never a call to GitHub.
  let last = "";
  let at = 0;
  app.hooks.status.push((st) => {
    const key = JSON.stringify(st.revs || {}) + (st.busy || "");
    if (key !== last || Date.now() - at > 30000) {
      last = key;
      at = Date.now();
      refreshChip();
    }
  });
  refreshChip();
}

// ---- Not committed ----------------------------------------------------------------

function blockItems(list) {
  return list.map((b) => [b.message, b.detail ? " " + b.detail : "", b.paths && b.paths.length ? " (" + b.paths.slice(0, 6).join(", ") + ")" : ""].join(""));
}

function sentences(described, empty) {
  if (!described.length) return h("p", { class: "muted" }, empty);
  return h("div", { class: "pub-said" }, described.map((d) => h("div", {},
    h("h3", {}, d.label),
    h("ul", { class: "pub-list" }, d.entries.map((e) => h("li", {}, h("span", {}, e.text),
      e.guarded ? h("span", { class: "badge gold" }, "Check this: " + e.label) : null))))));
}

async function notCommitted(body, app) {
  const msgs = h("div", { class: "msgs" });
  const out = h("div", {}, h("p", { class: "muted" }, "Reading the changes"));
  clear(body).append(msgs, out);
  let ch = null;
  let typed = null;             // the owner's own message, kept across a reload

  async function load() {
    try {
      ch = await api("GET", "publish/changes");
    } catch (e) {
      clear(out);
      msgs.append(banner({ tone: "critical", title: e.message }));
      return;
    }
    draw();
  }

  function draw() {
    const g = ch.groups;
    const mine = g.content.length + g.media.length + g.generated.length;
    clear(out);
    if (ch.blocking.length) out.append(banner({ tone: "critical", title: "Committing is not possible right now.", items: blockItems(ch.blocking) }));
    ch.warnings.forEach((w) => out.append(banner({ tone: "warning", title: w.message })));
    if (!mine) {
      out.append(h("section", { class: "card" }, h("h2", {}, "Nothing to commit"),
        h("p", {}, "Everything saved in the admin is already committed."),
        h("p", { class: "help" }, "Commits that are not on the live site yet are under ", h("a", { href: "#/publish/live" }, "Not live"), ".")));
    } else {
      out.append(h("div", { class: "two-col" },
        h("div", {}, customersCard(), filesCard()),
        commitCard()));
    }
    if (g.code.length || g.other.length) out.append(notIncludedCard());
  }

  function customersCard() {
    const g = ch.groups;
    const empty = g.media.length ? "Only photos or films changed; they are listed below." : "No content changed, only files the build makes.";
    return h("section", { class: "card" }, h("h2", {}, "What customers will see"), sentences(ch.described, empty));
  }

  function filesCard() {
    const g = ch.groups;
    const thumb = (it) => it.kind === "image" && it.change !== "deleted"
      ? h("img", { class: "pub-thumb", src: previewUrl(it.path), alt: "", loading: "lazy" }) : it.kind === "video" ? icon("film", 16) : null;
    return h("section", { class: "card" }, h("h2", {}, "In this commit"),
      g.content.length ? h("div", { class: "pub-group" }, h("h3", {}, "Content"), h("ul", { class: "pub-list" }, g.content.map((it) => pathRow(it)))) : null,
      g.media.length ? h("div", { class: "pub-group" }, h("h3", {}, "Photos and films"), h("ul", { class: "pub-list" }, g.media.map((it) => pathRow(it, thumb(it))))) : null,
      g.generated.length ? h("details", { class: "pub-group pub-more" },
        h("summary", {}, plural(g.generated.length, "generated file", "generated files"), h("span", { class: "muted" }, " made by the build from the content")),
        h("ul", { class: "pub-list" }, g.generated.map((it) => pathRow(it)))) : null);
  }

  function notIncludedCard() {
    const g = ch.groups;
    return h("section", { class: "card" }, h("h2", {}, "Not included"),
      h("p", { class: "help pub-lead" }, "Changed on this computer but not made by the admin. They stay out of the admin's commits; a developer commits them from Terminal."),
      h("ul", { class: "pub-list" },
        g.code.map((it) => pathRow(it, h("span", { class: "badge red" }, "Build code"))),
        g.other.map((it) => pathRow(it))));
  }

  function commitCard() {
    const subject = h("input", { id: "pub-subject", class: "input", value: typed ? typed.subject : ch.suggested_message, autocomplete: "off", spellcheck: "true",
      "aria-describedby": "pub-subject-help", oninput: () => { typed = { subject: subject.value, more: more.value }; count(); } });
    const more = h("textarea", { id: "pub-more", class: "input", rows: "3", value: typed ? typed.more : "",
      oninput: () => { typed = { subject: subject.value, more: more.value }; } });
    const counter = h("span", { class: "count", "aria-live": "polite" });
    const err = h("p", { class: "error", hidden: true });
    const btn = h("button", { class: "btn primary", type: "button", disabled: !ch.can_commit, onclick: () => commit() }, "Commit");
    function count() { counter.textContent = subject.value.trim().length + " of 72"; }
    count();

    async function commit() {
      const message = subject.value.trim() + (more.value.trim() ? "\n\n" + more.value.trim() : "");
      err.hidden = true;
      btn.disabled = true;
      btn.textContent = "Checking and committing";
      announce("Checking the commit. This takes a few seconds.");
      clear(msgs);
      try {
        const res = await api("POST", "publish/commit", { body: { message, paths_digest: ch.paths_digest } });
        typed = null;
        toast("Committed " + res.short + ". It is not live until you publish.", { action: { href: "#/publish/live", label: "Review and publish" } });
        if (res.left && res.left.length) msgs.append(banner({ tone: "warning", title: "Committed, but these still differ from the commit:", items: res.left }));
        refreshChip();
      } catch (e) {
        if (e.code === "validation") {
          err.textContent = e.message;
          err.hidden = false;
        } else if (e.code === "changes_moved") {
          msgs.append(banner({ tone: "warning", title: e.message, items: ["The list below is the new one. Your message is kept."] }));
        } else if (e.code === "checks_failed") {
          const rows = ((e.details && e.details.checks) || []).flatMap((c) => (c.paths && c.paths.length ? c.paths : []).concat(c.problems || []));
          msgs.append(banner({ tone: "critical", title: e.message, items: rows.slice(0, 12) }));
        } else if (e.code === "busy") {
          toast("Another change is still saving. Try again in a moment.");
        } else {
          msgs.append(banner({ tone: "critical", title: e.message }));
        }
      }
      await load();
    }

    return h("section", { class: "card pub-commit" }, h("h2", {}, "Commit"),
      h("div", { class: "field" }, h("div", { class: "f-head" }, h("label", { class: "f-label", for: "pub-subject" }, "Message"), counter), subject,
        h("p", { class: "help", id: "pub-subject-help" }, "One line of at most 72 characters saying what changed, like the repository's other commits. No long dashes and no sign-off lines."), err),
      h("div", { class: "field" }, h("label", { class: "f-label", for: "pub-more" }, "More detail (optional)"), more),
      btn,
      h("p", { class: "help" }, "Only the files listed here go in. First the admin rebuilds the site from exactly these files, the way both deploys will, and commits nothing if the result would differ. Committing does not publish."));
  }

  await load();
}

// ---- Not live ----------------------------------------------------------------------

function publishDialog(pv) {
  return new Promise((resolve) => {
    const d = h("dialog", { class: "dlg", "aria-labelledby": "pub-dlg-title" });
    const word = h("input", { id: "pub-word", class: "input", autocomplete: "off", spellcheck: "false", oninput: () => sync() });
    const tick = pv.external ? h("input", { id: "pub-ext", type: "checkbox", onchange: () => sync() }) : null;
    const go = h("button", { class: "btn primary", type: "button", disabled: true, onclick: () => done({ include: !!(tick && tick.checked) }) }, "Publish");
    // Focus goes back to the button that opened the dialog, so a keyboard
    // user is not left at the top of the page.
    const back = document.activeElement;
    const done = (v) => { d.close(); d.remove(); if (back && back.isConnected) back.focus(); resolve(v); };
    function sync() { go.disabled = word.value.trim() !== "PUBLISH" || (tick !== null && !tick.checked); }
    d.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
    word.addEventListener("keydown", (e) => { if (e.key === "Enter" && !go.disabled) { e.preventDefault(); go.click(); } });
    d.append(h("h2", { id: "pub-dlg-title" }, "Publish to the live site?"),
      h("p", {}, "This sends " + plural(pv.commits.length, "commit", "commits") + " to GitHub, ending at " + pv.local_sha.slice(0, 7) + ". "
        + plural(pv.published_count, "file changes", "files change") + " on the site, and " + pv.targets.join(" and ") + " start deploying."),
      tick ? h("label", { class: "check pub-tick", for: "pub-ext" }, tick,
        pv.external === 1 ? "Include the 1 commit made outside the admin. It goes live too." : "Include the " + pv.external + " commits made outside the admin. They go live too.") : null,
      h("div", { class: "field" }, h("label", { class: "f-label", for: "pub-word" }, "Type PUBLISH to confirm"), word),
      h("div", { class: "dlg-actions" }, h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"), go));
    document.body.append(d);
    d.showModal();
    word.focus();
  });
}

async function notLive(body, app) {
  const noPush = !!(app.state.session && app.state.session.no_push);
  const msgs = h("div", { class: "msgs" });
  const out = h("div", {}, h("p", { class: "muted" }, "Checking GitHub"));
  const stamp = h("span", { class: "muted" });
  const again = h("button", { class: "btn", type: "button", onclick: () => check() }, "Check GitHub again");
  const jobBox = h("div", { "aria-live": "polite" });
  clear(body).append(h("div", { class: "pub-bar" }, stamp, again), msgs, out);
  let pv = null;

  // GitHub is asked only here, on opening this tab and on "Check GitHub
  // again": never on a timer.
  async function check(keep) {
    again.disabled = true;
    if (!keep) clear(msgs);
    clear(out).append(h("p", { class: "muted" }, "Checking GitHub"));
    let offline = null;
    try { await api("POST", "publish/fetch", { body: {} }); } catch (e) { offline = e; }
    try {
      pv = await api("GET", "publish/preview");
    } catch (e) {
      clear(out);
      msgs.append(banner({ tone: "critical", title: e.message }));
      again.disabled = false;
      return;
    }
    again.disabled = false;
    if (offline) msgs.append(banner({ tone: "critical", title: offline.message, items: ["Nothing can be published until GitHub answers. Check the connection, then check again."] }));
    stamp.textContent = pv.fetched_at ? "GitHub checked " + when(pv.fetched_at) : "GitHub not checked since the admin started";
    draw();
  }

  function draw() {
    clear(out).append(checksCard());
    (pv.warnings || []).forEach((w) => out.append(banner({ tone: "warning", title: w.message,
      items: (w.paths || []).concat(w.count > (w.paths || []).length ? ["and " + (w.count - w.paths.length) + " more"] : []),
      actions: [h("a", { class: "btn", href: "#/publish" }, "Review and commit")] })));
    if (pv.commits.length) out.append(commitsCard(), h("div", { class: "cards two" }, customersCard(), filesCard()), ridingCard());
    out.append(publishCard());
  }

  function checksCard() {
    return h("section", { class: "card" }, h("h2", {}, "Before publishing"),
      h("ul", { class: "pub-list pub-checks" }, pv.checks.map((c) => h("li", { class: c.ok ? "ok" : "bad" },
        h("span", { class: "pub-mark" }, icon(c.ok ? "check" : "alert", 16)),
        h("span", {}, h("span", { class: "sr-only" }, c.ok ? "Passed: " : "Failed: "), c.label,
          c.detail ? h("span", { class: "pub-detail" }, c.detail) : null)))));
  }

  function commitsCard() {
    return h("section", { class: "card" }, h("h2", {}, plural(pv.commits.length, "commit goes live", "commits go live")),
      pv.external ? h("p", { class: "help pub-lead" }, plural(pv.external, "commit was", "commits were") + " made outside the admin, by a developer. They go live too, so the Publish dialog asks you to include them.") : null,
      h("ul", { class: "pub-list pub-commits" }, pv.commits.map((c) => h("li", {},
        h("div", { class: "pub-c-main" },
          h("span", { class: "pub-c-subject" }, c.subject),
          h("span", { class: "pub-detail" }, c.short + " by " + c.author + ", " + when(c.at)),
          c.files && c.files.length ? h("details", { class: "pub-more" }, h("summary", {}, plural(c.files.length, "file", "files")),
            h("ul", { class: "pub-list" }, c.files.map((f) => pathRow(f)))) : null),
        c.made_in_admin ? h("span", { class: "badge green" }, "Made in the admin") : h("span", { class: "badge amber" }, icon("alert", 12), "Made outside the admin")))));
  }

  function customersCard() {
    return h("section", { class: "card" }, h("h2", {}, "What customers will see"),
      sentences(pv.semantic, "No content changes. What changes is listed with the files."));
  }

  function filesCard() {
    const f = pv.published_files;
    const groups = KINDS.filter(([k]) => f[k] && f[k].length);
    const thumb = (k, it) => (k === "images" && it.change !== "deleted" && !it.dirty
      ? h("img", { class: "pub-thumb", src: previewUrl(it.path), alt: "", loading: "lazy" }) : null);
    return h("section", { class: "card" }, h("h2", {}, plural(pv.published_count, "file changes on the site", "files change on the site")),
      groups.length ? groups.map(([k, label]) => h("details", { class: "pub-group pub-more", open: f[k].length <= 8 },
        h("summary", {}, label + " (" + f[k].length + ")"),
        h("ul", { class: "pub-list" }, f[k].map((it) => pathRow(it, thumb(k, it))))))
        : h("p", { class: "muted" }, "None: these commits change only files the site does not serve."),
      h("p", { class: "help" }, "They go to " + pv.targets.join(" and ") + "."));
  }

  function ridingCard() {
    if (!pv.riding_along.length) return null;
    return h("section", { class: "card" }, h("h2", {}, "Rides along, not published"),
      h("p", { class: "help pub-lead" }, "These change in the repository with the push but are not part of the site."),
      h("ul", { class: "pub-list" }, pv.riding_along.map((it) => pathRow(it, h("span", { class: "badge" }, it.kind)))));
  }

  function publishCard() {
    const failed = pv.checks.filter((c) => !c.ok);
    let reason = "";
    if (noPush) reason = "This admin was started with --no-push, so publishing is switched off here. Start it without --no-push to publish.";
    else if (failed.length) reason = "Publishing waits until every check above passes.";
    const btn = h("button", { class: "btn primary", type: "button", disabled: !!reason || !pv.preview_id, "aria-describedby": reason ? "pub-why" : null,
      onclick: () => confirmPublish() }, icon("upload", 16), "Publish");
    return h("section", { class: "card pub-go" }, h("h2", {}, "Publish"),
      h("p", {}, pv.commits.length
        ? "Sends " + plural(pv.commits.length, "commit", "commits") + " to GitHub, ending at " + pv.local_sha.slice(0, 7) + ". Every publish starts two deploys, so it pays to publish several changes together."
        : "There is nothing to publish."),
      btn, reason ? h("p", { class: "help", id: "pub-why" }, reason) : null, jobBox);
  }

  async function confirmPublish() {
    const choice = await publishDialog(pv);
    if (!choice) return;
    clear(msgs);
    let res;
    try {
      res = await api("POST", "publish/push", { body: { preview_id: pv.preview_id, local_sha: pv.local_sha, remote_sha: pv.remote_sha,
        confirm: "PUBLISH", include_external: choice.include } });
    } catch (e) {
      msgs.append(banner({ tone: "critical", title: e.message }));
      if (e.code === "review_stale") check(true);
      return;
    }
    follow(res.job);
  }

  async function follow(job) {
    const line = h("span", {}, "Publishing");
    clear(jobBox).append(h("p", { class: "pub-job" }, h("span", { class: "pub-spin", "aria-hidden": "true" }), line));
    let j = job;
    while (j.state === "queued" || j.state === "running") {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        j = await api("GET", "jobs/" + j.id);
      } catch (e) {
        clear(jobBox).append(banner({ tone: "critical", title: e.message }));
        return;
      }
      if (j.log_tail && j.log_tail.length) line.textContent = j.log_tail[j.log_tail.length - 1];
    }
    clear(jobBox);
    if (j.state === "done") {
      const r = j.result || {};
      msgs.append(banner({ tone: "info", title: r.message,
        items: [r.confirmed ? "GitHub's main branch is now " + r.short + "." : "GitHub did not confirm the new commit when asked afterwards. Check GitHub again in a moment."] }));
      announce(r.message);
      refreshChip();
    } else {
      msgs.append(banner({ tone: "critical", title: (j.error && j.error.message) || "The publish did not finish.", items: ["Nothing is retried automatically."] }));
    }
    check(true);
  }

  await check();
}

// ---- Published ------------------------------------------------------------------------

async function publishedLog(body) {
  const out = h("div", {}, h("p", { class: "muted" }, "Reading the log"));
  clear(body).append(out);
  let log;
  try {
    log = await api("GET", "publish/log");
  } catch (e) {
    clear(out).append(banner({ tone: "critical", title: e.message }));
    return;
  }
  clear(out);
  const note = h("p", { class: "help" }, "This log is kept on this computer, in flow/content/.backups. It is how the admin knows which commits it made.");
  if (!log.items.length) {
    out.append(h("section", { class: "card" }, h("p", { class: "empty" }, "Nothing has been committed or published from this admin on this computer yet.")), note);
    return;
  }
  const what = (r) => (r.kind === "publish"
    ? [h("span", { class: "badge green" }, "Published"), " " + plural(r.commits || 0, "commit", "commits") + (r.outside ? ", " + r.outside + " made outside the admin" : "")
      + (r.remote_after === r.sha ? ". GitHub confirmed it." : ". GitHub had not confirmed it when asked afterwards.")]
    : [h("span", { class: "badge outline" }, "Committed"), " " + (r.subject || "") + (r.files ? " (" + plural(r.files, "file", "files") + ")" : "")]);
  out.append(h("section", { class: "card flush" }, h("div", { class: "table-wrap" }, h("table", { class: "table pub-log" },
    h("caption", { class: "sr-only" }, "Commits and publishes made in this admin, newest first"),
    h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "When"), h("th", { scope: "col" }, "What"), h("th", { scope: "col" }, "Commit"))),
    h("tbody", {}, log.items.map((r) => h("tr", {},
      h("td", { class: "num" }, when(r.at)), h("td", {}, what(r)), h("td", { class: "pub-path" }, (r.sha || "").slice(0, 7)))))))),
  note);
}
